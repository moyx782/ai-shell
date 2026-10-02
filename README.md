# AI Shell

一个基于 OpenCode 的常驻终端 REPL。v0.2.0 起提供 Go 编译的独立可执行文件，运行时不需要 Python、Node.js 或 Go；继续使用本机的 OpenCode、供应商配置和会话记录。运行 `ai` 进入 `ai>`，每轮任务完成后继续输入。

```text
$ ai
ai> 分析当前项目结构
ai> 修复刚才发现的问题
ai> 运行测试
ai> /model
ai> exit
```

## 安装与部署

支持 Linux、macOS 的 x86_64/ARM64，以及 Windows WSL。运行需要本机 OpenCode；安装脚本需要 Bash、curl、常见系统工具和 SHA256 校验工具（Linux 的 sha256sum 或 macOS 的 shasum）。Git 仅用于克隆和 Git 命令，ripgrep 可选。

直接下载安装脚本，不需要 Git 或 Python：

```bash
curl -fL https://github.com/moyx782/ai-shell/releases/download/v0.2.0/install.sh -o install-ai.sh
bash install-ai.sh
export PATH="$HOME/.local/bin:$PATH"
ai
```

或者克隆后安装：

```bash
git clone https://github.com/moyx782/ai-shell.git
cd ai-shell
bash install.sh
export PATH="$HOME/.local/bin:$PATH"
```

安装程序自动选择系统和 CPU 架构，下载预编译程序，验证 SHA256，备份已有 `ai`，最后替换安装，不使用 sudo。下载时显示百分比、已下载字节、平均/当前速度、已用时间和预计剩余时间；服务器未提供长度或传输刚开始时，部分数值可能显示为 `--:--:--`。这些指标是文件下载进度，不是模型生成速度。可选 OpenCode 安装阶段的显示由其官方安装器控制。

没有 OpenCode 时可运行 `bash install.sh --install-opencode`，仅在缺失时调用其[官方安装脚本](https://opencode.ai/docs/#install)。本项目不会把 OpenCode 打包进 `ai`。已有 OpenCode 时直接复用。

也可从 [Release](https://github.com/moyx782/ai-shell/releases/tag/v0.2.0) 下载对应的单文件，赋予执行权限后运行。例如 Linux x86_64：

```bash
chmod +x ai-linux-amd64
./ai-linux-amd64 --plan
```

离线安装已经下载的程序（模型服务通常仍需要网络）：

```bash
bash install.sh --binary ./ai-linux-amd64 --bin-dir "$HOME/bin"
```

将上面的 `export PATH=...` 加入 `~/.bashrc` 或 `~/.zshrc`，可让新终端继续使用 `ai`。AI Shell 安装脚本本身不改 shell 配置；可选的 OpenCode 官方安装程序可能修改配置。自定义位置：

```bash
bash install.sh --bin-dir "$HOME/bin"
```

首次配置模型供应商：

```bash
opencode auth login
opencode models
cd /path/to/your/project
ai
```

模型凭据、供应商配置、MCP、工具和权限使用本机 OpenCode 的设置，仓库不包含个人配置或密钥。安装程序不为你配置供应商账号。

## 交互命令

| 命令 | 作用 |
| --- | --- |
| `/help` | 查看帮助 |
| `/model`、`/model list`、`/models` | 显示模型覆盖设置并列出可用模型 |
| `/model provider/model` | 下一轮切换到指定模型，保留对话 |
| `/model default` | 取消覆盖，由 OpenCode 按会话或配置选择模型 |
| `/plan [任务]` | 切换到规划模式，可同时发送任务，保留会话 |
| `/build [任务]` | 切换到执行模式，可同时发送任务，保留会话 |
| `/status` | 当前目录、会话 ID、模型与 agent 设置、Git 状态 |
| `/git` | 未暂存的 Git diff |
| `/files` | 最多列出 200 个项目文件；没有 rg 时仅列当前目录 |
| `/run npm test` | 通过本地 shell 执行命令 |
| `/cd "路径"` | 切换目录，同时重置会话 |
| `/new` | 新建对话，保留模型覆盖设置 |
| `/login` | 使用本机 OpenCode 配置模型供应商 |
| `exit`、`quit`、`/exit`、`/quit` | 退出 |

Ctrl-C 中断任务并返回提示符，Ctrl-D 退出。方向键可浏览当前进程内的输入历史，Tab 补全内置命令；历史不会由本程序写入文件。`/run` 的输出显示在终端，不会自动加入模型对话；需要模型读取测试结果时，直接输入“运行测试并分析结果”。

`/model` 接受 `opencode models` 列表中的完整模型 ID。只检查 ID 格式；实际可用性和账号权限由 OpenCode 在请求时验证。

## 启动参数与恢复会话

```bash
ai --help
ai --version
ai --licenses
ai --model provider/model
ai --agent build
ai --plan
ai --agent plan "先分析问题，给出实施计划"
ai "分析当前项目"
ai --session ses_example --model provider/model
ai --backend --version
```

退出时会打印恢复命令，包含当前 session ID 和显式设置的模型、agent。请在原项目目录运行该命令。新启动的 `ai` 默认新建会话，不会自动续接其他终端的最近对话。

启动选项放在任务文本之前。`--backend` 必须作为第一个参数，后续参数直接交给本机 OpenCode；例如 `ai --backend auth login`。默认从 PATH 查找 OpenCode，再尝试 `~/.opencode/bin/opencode`；也可用 `AI_SHELL_BACKEND=/absolute/path/to/opencode ai` 显式指定。

## 先规划，再执行

```text
ai> /plan
ai[plan]> 分析登录问题，先给出修改计划
ai[plan]> 调整第二步，补充测试方案
ai[plan]> /build
ai[build]> 按刚才的计划实施
```

也可以直接输入 `/plan 分析登录问题` 或 `/build 按计划实施`。模式会持续到下一次切换，`/new` 和 `/cd` 重置会话但保留当前 agent。`ai --plan` 等同于 `ai --agent plan`。

规划模式实际传递 `--agent plan`，使用 [OpenCode 的 Plan agent](https://opencode.ai/docs/agents/#use-plan)。具体工具权限由 OpenCode 版本及本机、项目配置决定，不是操作系统级只读沙箱；OpenCode 可能允许写入计划文件。显式的 `/run` 仍直接执行本地命令，不受 Plan agent 约束。切换 `/build` 本身不会开始执行，需要再发送任务。

## 更新与卸载

在克隆目录执行：

```bash
git pull --ff-only
bash install.sh
```

如果使用过 `--bin-dir`，更新时传入相同参数。备份位于安装目录，名称为 `ai.backup-时间戳`；需要回滚时将所需备份复制回 `ai`。

卸载默认安装：

```bash
rm "$HOME/.local/bin/ai"
```

卸载不删除 OpenCode、会话记录、供应商凭据或旧备份。

## 实现与限制

Go REPL 每轮调用 `opencode run --format json`，从事件读取 session ID，后续使用 `--session`。OpenCode 负责模型调用与工具执行；本项目负责命令交互和输出呈现。Go 和行编辑库编译进二进制；Linux 版本以 `CGO_ENABLED=0` 构建，不依赖 Python 或 glibc。macOS 版本使用系统提供的运行接口。项目自身的编译、测试工具仍需按项目要求安装。

本项目不实现 OpenCode TUI 中的权限审批或交互提问界面，也不自动开启 `--auto`。需要这类交互时，可在原项目目录通过 `opencode --session <会话ID>` 使用 OpenCode 本身。具体工具权限行为取决于安装的 OpenCode 版本和配置。

本机已核对 OpenCode 1.18.33 的 CLI 参数。自动化测试使用模拟后端，不发送模型请求，也不证明所有 OpenCode 版本或供应商兼容。

## 开发与测试

以下依赖只用于开发和测试：Go 1.23+、Python 3.9+。普通用户下载发行版即可。

```bash
bash -n install.sh
go test ./...
python3 -m unittest discover -s tests -v
bash scripts/build.sh
```

`scripts/build.sh` 交叉编译 Linux/macOS × amd64/arm64 四种程序到 `dist/native/`，并生成 `SHA256SUMS`。GitHub Actions 在 Linux/macOS 上执行自动化测试，覆盖会话续接、模型切换、错误处理、命令执行、安装升级及没有 Python/Node.js 的运行环境。

第三方许可证随二进制内置，可通过 `ai --licenses` 查看。旧 Python 实现保留在 Git 历史和 v0.1.1 Release 中。
