package backend

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

func Resolve() (string, error) {
	if override := os.Getenv("AI_SHELL_BACKEND"); override != "" {
		path, err := exec.LookPath(override)
		if err != nil {
			return "", err
		}
		return filepath.Abs(path)
	}
	path, err := exec.LookPath("opencode")
	if err != nil {
		home, homeErr := os.UserHomeDir()
		if homeErr == nil {
			candidate := filepath.Join(home, ".opencode", "bin", "opencode")
			if info, statErr := os.Stat(candidate); statErr == nil && info.Mode().IsRegular() && info.Mode()&0111 != 0 {
				return candidate, nil
			}
		}
		return "", fmt.Errorf("找不到 OpenCode；请先安装，或通过 AI_SHELL_BACKEND 指定可执行文件路径")
	}
	return filepath.Abs(path)
}
