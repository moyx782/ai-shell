package main

import (
	"bufio"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
	"time"
	"unicode"

	"github.com/moyx782/ai-shell/internal/backend"
	"github.com/moyx782/ai-shell/internal/notices"
	"github.com/peterh/liner"
	"golang.org/x/sys/unix"
)

const version = "0.2.0"
const help = `直接输入任务，回车发送。
/help              显示帮助
/model [提供商/模型] 列出或切换模型
/model default     取消模型覆盖
/plan [任务]       切换规划模式，可同时发送任务
/build [任务]      切换执行模式，可同时发送任务
/status            目录、会话、模型、agent 和 Git 状态
/git               查看 Git diff
/files             列出文件（最多 200 个）
/run 命令          执行本地 shell 命令
/cd 路径           切换目录并重置会话
/new               重置会话
/login             配置本机 OpenCode 的模型供应商
/exit              退出（也可使用 exit、quit 或 Ctrl-D）
Ctrl-C             中断任务或取消输入
`

type shell struct{ model, agent, session, backend string }

func quote(value string) string {
	if value != "" && strings.IndexFunc(value, func(r rune) bool {
		return !(unicode.IsLetter(r) || unicode.IsDigit(r) || strings.ContainsRune("_@%+=:,./-", r))
	}) == -1 {
		return value
	}
	return "'" + strings.ReplaceAll(value, "'", "'\"'\"'") + "'"
}

// Children run in their own process group. Interrupt the group, then kill it if
// it does not exit, while the parent remains available for the next prompt.
func run(command *exec.Cmd) error {
	command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if command.Stdin == os.Stdin {
		fd := int(os.Stdin.Fd())
		if group, err := unix.IoctlGetInt(fd, unix.TIOCGPGRP); err == nil {
			command.SysProcAttr.Foreground = true
			command.SysProcAttr.Ctty = fd
			defer func() {
				signal.Ignore(syscall.SIGTTOU)
				_ = unix.IoctlSetPointerInt(fd, unix.TIOCSPGRP, group)
				signal.Reset(syscall.SIGTTOU)
			}()
		}
	}
	interrupts := make(chan os.Signal, 2)
	signal.Notify(interrupts, os.Interrupt)
	defer signal.Stop(interrupts)
	if err := command.Start(); err != nil {
		return err
	}
	done := make(chan error, 1)
	go func() { done <- command.Wait() }()
	select {
	case err := <-done:
		return err
	case <-interrupts:
		_ = syscall.Kill(-command.Process.Pid, syscall.SIGINT)
		select {
		case <-done:
		case <-time.After(3 * time.Second):
			_ = syscall.Kill(-command.Process.Pid, syscall.SIGKILL)
			<-done
		}
		fmt.Println("\n[已中断，返回 REPL]")
		return nil
	}
}

func local(name string, args ...string) {
	command := exec.Command(name, args...)
	command.Stdin, command.Stdout, command.Stderr = os.Stdin, os.Stdout, os.Stderr
	if err := run(command); err != nil {
		fmt.Printf("[命令错误：%v]\n", err)
	}
}

type event struct {
	Type    string          `json:"type"`
	Session string          `json:"sessionID"`
	Error   json.RawMessage `json:"error"`
	Part    struct {
		Text  string `json:"text"`
		Tool  string `json:"tool"`
		State struct {
			Status string `json:"status"`
			Output string `json:"output"`
			Error  string `json:"error"`
		} `json:"state"`
	} `json:"part"`
}

func (s *shell) render(reader io.Reader) {
	// ReadString handles large tool outputs without Scanner's token size limit.
	input := bufio.NewReader(reader)
	for {
		line, err := input.ReadString('\n')
		if line != "" {
			var item event
			if json.Unmarshal([]byte(line), &item) != nil || item.Type == "" {
				fmt.Print(line)
			} else {
				if item.Session != "" {
					s.session = item.Session
				}
				switch item.Type {
				case "text":
					fmt.Println(item.Part.Text)
				case "tool_use":
					fmt.Printf("[工具：%s · %s]\n", item.Part.Tool, item.Part.State.Status)
					if item.Part.State.Output != "" {
						fmt.Println(item.Part.State.Output)
					}
					if item.Part.State.Error != "" {
						fmt.Println(item.Part.State.Error)
					}
				case "error":
					fmt.Printf("[OpenCode 错误] %s\n", item.Error)
				}
			}
		}
		if err != nil {
			break
		}
	}
}

func (s *shell) ask(prompt string) {
	args := []string{"run", "--format", "json"}
	if s.session != "" {
		args = append(args, "--session", s.session)
	}
	if s.model != "" {
		args = append(args, "--model", s.model)
	}
	if s.agent != "" {
		args = append(args, "--agent", s.agent)
	}
	args = append(args, "--", prompt)
	command := exec.Command(s.backend, args...)
	command.Stderr = os.Stderr
	reader, writer := io.Pipe()
	command.Stdout = writer
	rendered := make(chan struct{})
	go func() { s.render(reader); close(rendered) }()
	err := run(command)
	writer.Close()
	<-rendered
	reader.Close()
	if err != nil {
		fmt.Printf("[OpenCode 退出码或启动错误：%v]\n", err)
	}
	if s.session == "" {
		fmt.Println("[尚未获得会话 ID；下一轮将创建新会话]")
	}
}

func listFiles() {
	if _, err := exec.LookPath("rg"); err == nil {
		command := exec.Command("rg", "--files")
		command.Stderr = os.Stderr
		output, err := command.Output()
		if err != nil && len(output) == 0 {
			fmt.Println("[没有文件或 rg 执行失败]")
			return
		}
		lines := strings.Split(strings.TrimSuffix(string(output), "\n"), "\n")
		count := len(lines)
		if count > 200 {
			lines = lines[:200]
		}
		fmt.Println(strings.Join(lines, "\n"))
		if count > 200 {
			fmt.Printf("[共 %d 个文件，仅显示前 200 个]\n", count)
		}
		return
	}
	entries, err := os.ReadDir(".")
	if err != nil {
		fmt.Println(err)
		return
	}
	for i, entry := range entries {
		if i == 200 {
			break
		}
		fmt.Println(entry.Name())
	}
}

func changeDirectory(argument string) error {
	path := strings.TrimSpace(argument)
	// A directory is one argument; accept raw spaces or a matching quote pair.
	if len(path) > 0 && (path[0] == '\'' || path[0] == '"') {
		if len(path) < 2 || path[len(path)-1] != path[0] {
			return errors.New("路径引号未闭合")
		}
		path = path[1 : len(path)-1]
	}
	if path == "" || path == "~" || strings.HasPrefix(path, "~/") {
		home, err := os.UserHomeDir()
		if err != nil {
			return err
		}
		path = filepath.Join(home, strings.TrimPrefix(strings.TrimPrefix(path, "~"), "/"))
	}
	return os.Chdir(path)
}

func (s *shell) handle(command string) bool {
	command = strings.TrimSpace(command)
	if command == "" {
		return true
	}
	if command == "exit" || command == "quit" || command == "/exit" || command == "/quit" {
		return false
	}
	name, argument := command, ""
	if index := strings.IndexFunc(command, unicode.IsSpace); index >= 0 {
		name, argument = command[:index], strings.TrimSpace(command[index:])
	}
	switch name {
	case "/help":
		fmt.Print(help)
	case "/plan", "/build":
		s.agent = name[1:]
		fmt.Printf("[已切换到 %s 模式；保留当前会话]\n", s.agent)
		if argument != "" {
			s.ask(argument)
		}
	case "/model", "/models":
		switch argument {
		case "", "list":
			fmt.Printf("模型设置：%s\n", fallback(s.model))
			local(s.backend, "models")
			fmt.Println("使用 /model 提供商/模型 切换；/model default 取消覆盖。")
		case "default":
			s.model = ""
			fmt.Println("[已取消模型覆盖]")
		default:
			parts := strings.SplitN(argument, "/", 2)
			if len(parts) != 2 || parts[0] == "" || parts[1] == "" || strings.IndexFunc(argument, unicode.IsSpace) >= 0 {
				fmt.Println("用法：/model 提供商/模型")
			} else {
				s.model = argument
				fmt.Printf("[模型已设为 %s；下一轮生效，保留当前会话]\n", argument)
			}
		}
	case "/new":
		s.session = ""
		fmt.Println("[新会话将在下次发送任务时创建]")
	case "/status":
		cwd, _ := os.Getwd()
		fmt.Printf("目录：%s\n会话：%s\n模型设置：%s\nAgent：%s\n后端：%s\n", cwd, fallback(s.session), fallback(s.model), fallback(s.agent), s.backend)
		local("git", "status", "--short", "--branch")
	case "/git":
		local("git", "--no-pager", "diff")
	case "/files":
		listFiles()
	case "/run":
		if argument == "" {
			fmt.Println("用法：/run npm test")
		} else {
			local("/bin/sh", "-c", argument)
		}
	case "/cd":
		if err := changeDirectory(argument); err != nil {
			fmt.Printf("[错误：%v]\n", err)
		} else {
			s.session = ""
			cwd, _ := os.Getwd()
			fmt.Printf("[目录：%s；已切换到新会话]\n", cwd)
		}
	case "/login":
		command := exec.Command(s.backend, "auth", "login")
		command.Stdin, command.Stdout, command.Stderr = os.Stdin, os.Stdout, os.Stderr
		interrupts := make(chan os.Signal, 1)
		signal.Notify(interrupts, os.Interrupt)
		if err := command.Run(); err != nil {
			fmt.Printf("[登录已结束：%v]\n", err)
		}
		signal.Stop(interrupts)
	default:
		if strings.HasPrefix(command, "/") {
			fmt.Println("未知命令，输入 /help 查看帮助。")
		} else {
			s.ask(command)
		}
	}
	return true
}

func fallback(value string) string {
	if value == "" {
		return "由 OpenCode 选择（未指定覆盖）"
	}
	return value
}

func main() { os.Exit(start()) }

func start() int {
	// Expose the selected local backend for authentication and configuration.
	if len(os.Args) > 1 && os.Args[1] == "--backend" {
		path, err := backend.Resolve()
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
		command := exec.Command(path, os.Args[2:]...)
		command.Stdin, command.Stdout, command.Stderr = os.Stdin, os.Stdout, os.Stderr
		// This is a foreground interactive program (auth login / TUI); keep its TTY.
		if err := command.Run(); err != nil {
			if exit, ok := err.(*exec.ExitError); ok {
				return exit.ExitCode()
			}
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
		return 0
	}
	var s shell
	flags := flag.NewFlagSet("ai", flag.ContinueOnError)
	flags.StringVar(&s.model, "model", "", "模型 provider/model")
	flags.StringVar(&s.model, "m", "", "模型 provider/model")
	flags.StringVar(&s.agent, "agent", "", "OpenCode agent，例如 plan 或 build")
	flags.StringVar(&s.session, "session", "", "恢复会话 ID")
	flags.StringVar(&s.session, "s", "", "恢复会话 ID")
	plan := flags.Bool("plan", false, "以规划模式启动")
	showVersion := flags.Bool("version", false, "显示版本")
	showLicenses := flags.Bool("licenses", false, "显示内置第三方许可")
	flags.Usage = func() {
		fmt.Fprint(flags.Output(), "Usage: ai [--plan] [--model provider/model] [--session ID] [任务]\n       ai --backend <OpenCode 参数>\n\n")
		flags.PrintDefaults()
	}
	if err := flags.Parse(os.Args[1:]); err != nil {
		if err == flag.ErrHelp {
			return 0
		}
		return 2
	}
	if *showVersion {
		fmt.Println("ai-shell " + version)
		return 0
	}
	if *showLicenses {
		fmt.Print(notices.Text)
		return 0
	}
	if *plan {
		if s.agent != "" {
			fmt.Fprintln(os.Stderr, "--plan 和 --agent 不能同时使用")
			return 2
		}
		s.agent = "plan"
	}
	path, err := backend.Resolve()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	s.backend = path
	// Keep Ctrl-C from terminating the REPL between a prompt and child startup.
	// Active child execution registers its own interrupt handler in run().
	interrupts := make(chan os.Signal, 1)
	signal.Notify(interrupts, os.Interrupt)
	defer signal.Stop(interrupts)
	fmt.Println("╭────────────────────╮\n│  AI Coding Shell   │\n╰────────────────────╯\n输入 /help 查看命令；exit 退出。")
	line := liner.NewLiner()
	defer line.Close()
	line.SetCtrlCAborts(true)
	commands := []string{"/help", "/model", "/plan", "/build", "/status", "/git", "/files", "/run", "/cd", "/new", "/login", "/exit"}
	sort.Strings(commands)
	line.SetCompleter(func(prefix string) []string {
		var matches []string
		for _, item := range commands {
			if strings.HasPrefix(item, prefix) {
				matches = append(matches, item)
			}
		}
		return matches
	})
	pending := strings.Join(flags.Args(), " ")
	for {
		prompt := "ai> "
		if s.agent != "" {
			prompt = "ai[" + s.agent + "]> "
		}
		command := pending
		pending = ""
		if command == "" {
			command, err = line.Prompt(prompt)
			if err == liner.ErrPromptAborted {
				fmt.Println("[已取消输入]")
				continue
			}
			if err == io.EOF {
				fmt.Println()
				break
			}
			if err != nil {
				fmt.Fprintln(os.Stderr, err)
				break
			}
		}
		if strings.TrimSpace(command) != "" {
			line.AppendHistory(command)
		}
		if !s.handle(command) {
			break
		}
	}
	if s.session != "" {
		resume := "ai --session " + quote(s.session)
		if s.model != "" {
			resume += " --model " + quote(s.model)
		}
		if s.agent != "" {
			resume += " --agent " + quote(s.agent)
		}
		fmt.Println("恢复本次会话：" + resume)
	}
	return 0
}
