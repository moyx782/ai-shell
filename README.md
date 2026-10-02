# AI Shell

一个基于 OpenCode 的常驻终端 REPL。运行 `ai` 进入 `ai>`，每轮任务完成后继续输入；通过明确的 OpenCode session ID 保留对话上下文。

```text
$ ai
ai> 分析当前项目结构
ai> 修复刚才发现的问题
ai> 运行测试
ai> /model
ai> exit
```

## 安装与部署

支持 Linux、macOS 和 Windows WSL。需要 Python 3.8+、Bash 和 OpenCode；Python 部分仅使用标准库。Git 用于克隆和 Git 命令，ripgrep 可选，用于递归列出文件。

```bash
git clone https://github.com/moyx782/ai-shell.git
cd ai-shell
bash install.sh --install-opencode
export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"
```

`--install-opencode` 仅在找不到 OpenCode 时运行其[官方安装脚本](https://opencode.ai/docs/#install)。已有 OpenCode 时直接运行 `bash install.sh` 即可。安装脚本会检测 Python 版本、安装可执行文件，并在覆盖前备份已有的 `ai`，不使用 sudo。OpenCode 安装和模型请求需要联网。

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
| `/status` | 当前目录、会话 ID、模型覆盖设置与 Git 状态 |
| `/git` | 未暂存的 Git diff |
| `/files` | 最多列出 200 个项目文件；没有 rg 时仅列当前目录 |
| `/run npm test` | 通过本地 shell 执行命令 |
| `/cd "路径"` | 切换目录，同时重置会话 |
| `/new` | 新建对话，保留模型覆盖设置 |
| `exit`、`quit`、`/exit`、`/quit` | 退出 |

Ctrl-C 中断任务并返回提示符，Ctrl-D 退出。方向键可浏览当前进程内的输入历史，历史不会由本程序写入文件。`/run` 的输出显示在终端，不会自动加入模型对话；需要模型读取测试结果时，直接输入“运行测试并分析结果”。

`/model` 接受 `opencode models` 列表中的完整模型 ID。只检查 ID 格式；实际可用性和账号权限由 OpenCode 在请求时验证。

## 启动参数与恢复会话

```bash
ai --help
ai --version
ai --model provider/model
ai --agent build
ai "分析当前项目"
ai --session ses_example --model provider/model
```

退出时会打印恢复命令，包含当前 session ID 和显式设置的模型、agent。请在原项目目录运行该命令。新启动的 `ai` 默认新建会话，不会自动续接其他终端的最近对话。

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

Python REPL 每轮调用 `opencode run --format json`，从事件读取 session ID，后续使用 `--session`。OpenCode 负责模型调用与工具执行；本项目负责命令交互和输出呈现。没有额外 Python 依赖。

本项目不实现 OpenCode TUI 中的权限审批或交互提问界面，也不自动开启 `--auto`。需要这类交互时，可在原项目目录通过 `opencode --session <会话ID>` 使用 OpenCode 本身。具体工具权限行为取决于安装的 OpenCode 版本和配置。

本机已核对 OpenCode 1.18.33 的 CLI 参数。自动化测试使用模拟后端，不发送模型请求，也不证明所有 OpenCode 版本或供应商兼容。

## 开发与测试

```bash
bash -n install.sh
python3 -m unittest discover -s tests -v
```

GitHub Actions 在 Linux/macOS、Python 3.9/3.13 上执行测试，覆盖会话续接、模型切换、错误处理、命令执行和安装升级。

发布包可解压后运行 `bash install.sh`，也可直接运行 `python3 bin/ai`。
