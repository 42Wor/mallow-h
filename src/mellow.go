package src

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const historyDir = ".mellow/history"

var ignoredDirs = map[string]bool{
	".git":         true,
	".mellow":      true,
	"node_modules": true,
	"venv":         true,
	".venv":        true,
	"dist":         true,
	"build":        true,
	".vscode":      true,
	"__pycache__":  true,
	"target":       true,
}

var ignoredExts = map[string]bool{
	".png":   true,
	".jpg":   true,
	".jpeg":  true,
	".gif":   true,
	".ico":   true,
	".svg":   true,
	".zip":   true,
	".tar":   true,
	".gz":    true,
	".pdf":   true,
	".exe":   true,
	".dll":   true,
	".dylib": true,
	".so":    true,
	".bin":   true,
	".mp3":   true,
	".mp4":   true,
	".wav":   true,
}

func Execute() {
	args := os.Args[1:]
	if len(args) == 0 || args[0] == "help" {
		PrintHelp()
		return
	}

	if args[0] == "init" {
		scanCodebase := false
		for _, arg := range args[1:] {
			if arg == "-d" || arg == "--codebase" {
				scanCodebase = true
			}
		}
		InitMellow(scanCodebase)
		return
	}

	if args[0] == "apply" {
		containerFile := "container.txt"
		if len(args) > 1 {
			containerFile = args[1]
		}
		ApplyChanges(containerFile)
		return
	}

	fmt.Println("❌ Unknown command. Run 'mellow help' for usage.")
}

func PrintHelp() {
	fmt.Println("🚀 Mellow CLI - LLM Code Harness")
	fmt.Println("Usage:")
	fmt.Println("  mellow init               - Initialize the .mellow history folder, container.txt, and mellow_prompt.md")
	fmt.Println("  mellow init -d            - Scan project directory, clean up old outputs, and build a full codebase prompt context")
	fmt.Println("  mellow apply [file.txt]   - Apply changes from container.txt (defaults to container.txt)")
}

// isCriticalFile checks if a file is a critical system config file or documentation.
func isCriticalFile(path string) bool {
	name := strings.ToLower(filepath.Base(path))
	ext := strings.ToLower(filepath.Ext(path))

	criticalFiles := map[string]bool{
		"container.txt":    true,
		"mellow_prompt.md": true,
		"metadata.txt":     true,
		"mellow":           true,
		"mellow-h":         true,
	}

	return criticalFiles[name] || ext == ".md"
}

// logError prints the error to stdout and appends the trace to metadata.txt
func logError(message string) {
	fmt.Println(message)

	f, err := os.OpenFile("metadata.txt", os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	defer f.Close()

	timestamp := time.Now().Format("2006-01-02 15:04:05")
	_, _ = f.WriteString(fmt.Sprintf("[%s] ERROR: %s\n", timestamp, message))
}

func isIgnored(path string) bool {
	parts := strings.Split(path, string(filepath.Separator))
	for _, part := range parts {
		if ignoredDirs[part] {
			return true
		}
	}
	return false
}

func buildTree(dir string, indent string, builder *strings.Builder) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}

	var validEntries []os.DirEntry
	for _, entry := range entries {
		name := entry.Name()
		if !ignoredDirs[name] && !isCriticalFile(name) {
			validEntries = append(validEntries, entry)
		}
	}

	for i, entry := range validEntries {
		name := entry.Name()
		isLast := i == len(validEntries)-1
		prefix := "├── "
		if isLast {
			prefix = "└── "
		}

		builder.WriteString(indent + prefix + name + "\n")

		if entry.IsDir() {
			nextIndent := indent + "│   "
			if isLast {
				nextIndent = indent + "    "
			}
			buildTree(filepath.Join(dir, name), nextIndent, builder)
		}
	}
}

func updateGitignore() {
	gitignorePath := ".gitignore"
	ignoredEntries := []string{
		"container.txt",
		"metadata.txt",
		"mellow_prompt.md",
		".mellow/",
		".env",
		"mellow.toml",
	}

	var content string
	if bytes, err := os.ReadFile(gitignorePath); err == nil {
		content = string(bytes)
	}

	var toAdd []string
	for _, item := range ignoredEntries {
		if !strings.Contains(content, item) {
			toAdd = append(toAdd, item)
		}
	}

	if len(toAdd) == 0 {
		return
	}

	f, err := os.OpenFile(gitignorePath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	defer f.Close()

	if len(content) > 0 && !strings.HasSuffix(content, "\n") {
		f.WriteString("\n")
	}
	f.WriteString("\n# Mellow CLI\n")
	for _, item := range toAdd {
		f.WriteString(item + "\n")
	}
	fmt.Println("✅ Updated .gitignore with Mellow system rules.")
}

func InitMellow(scanCodebase bool) {
	err := os.MkdirAll(historyDir, 0755)
	if err != nil {
		fmt.Printf("❌ Failed to create %s: %v\n", historyDir, err)
		return
	}

	if _, err := os.Stat("container.txt"); os.IsNotExist(err) {
		err = os.WriteFile("container.txt", []byte(""), 0644)
		if err != nil {
			fmt.Printf("❌ Failed to create container.txt: %v\n", err)
			return
		}
	}

	if _, err := os.Stat("metadata.txt"); os.IsNotExist(err) {
		err = os.WriteFile("metadata.txt", []byte(""), 0644)
		if err != nil {
			fmt.Printf("❌ Failed to create metadata.txt: %v\n", err)
			return
		}
	}

	// Safely register Mellow configuration files inside gitignore
	updateGitignore()

	promptPath := "mellow_prompt.md"
	if scanCodebase {
		_ = os.Remove(promptPath)
	} else {
		if _, err := os.Stat(promptPath); err == nil {
			fmt.Println("✅ mellow_prompt.md already exists. Run with '-d' to overwrite and include codebase context.")
			return
		}
	}

	promptContent := `# Mellow CLI - AI Agent Instructions

You are an AI coding assistant. Whenever I ask you to modify, create, or delete code, DO NOT output the entire file. To save tokens and ensure exact modifications, you MUST output your changes strictly in the following format. I will parse your output using the ` + "`mellow`" + ` CLI tool.

## Format Rules

### 1. To Create a New File
[FILE] path/to/new_file.ext
[CREATE]
<exact lines of code to insert>
[END]

### 2. To Modify an Existing File
[FILE] path/to/existing_file.ext
[SEARCH]
<exact lines of code to find - must match exactly including indentation>
[REPLACE]
<new lines of code to replace the searched lines>
[END]

### 3. To Delete Code Snippet
[FILE] path/to/existing_file.ext
[DELETE]
<exact lines of code to remove>
[END]

### 4. To Delete Entire File
[FILE] path/to/file.ext
[DELETE_FILE]
[END]

## Important Constraints:
1. The [SEARCH] block must match the existing code *exactly*, including indentation and spacing.
2. Include enough context in the [SEARCH] block so it is unique within the file.
3. Do not use markdown code blocks ("` + "```" + `") around the format. Just output the raw text.
4. You can output multiple blocks for multiple files or multiple changes in the same file.`

	var builder strings.Builder
	builder.WriteString(promptContent)

	if scanCodebase {
		fmt.Println("🔍 Scanning project codebase directory tree...")
		var treeBuilder strings.Builder
		buildTree(".", "", &treeBuilder)

		builder.WriteString("\n\n## Project Directory Tree\n```text\n")
		builder.WriteString(treeBuilder.String())
		builder.WriteString("```\n")

		fmt.Println("📄 Reading project source files...")
		var sourceBuilder strings.Builder
		err := filepath.WalkDir(".", func(path string, d os.DirEntry, err error) error {
			if err != nil {
				return err
			}
			if d.IsDir() {
				if ignoredDirs[d.Name()] {
					return filepath.SkipDir
				}
				return nil
			}

			if isIgnored(path) {
				return nil
			}

			if isCriticalFile(path) {
				return nil
			}

			ext := strings.ToLower(filepath.Ext(path))
			if ignoredExts[ext] {
				return nil
			}

			content, err := os.ReadFile(path)
			if err != nil {
				return nil
			}

			sourceBuilder.WriteString(fmt.Sprintf("\n\n====================\nFILE PATH: %s\n====================\n\n", path))
			sourceBuilder.Write(content)
			return nil
		})

		if err == nil {
			builder.WriteString("\n\n## Project Files Source Code\n")
			builder.WriteString(sourceBuilder.String())
		}
	}

	err = os.WriteFile(promptPath, []byte(builder.String()), 0644)
	if err != nil {
		fmt.Printf("❌ Failed to write mellow_prompt.md: %v\n", err)
		return
	}

	fmt.Println("✅ Initialized .mellow history folder.")
	fmt.Println("✅ Created container.txt")
	if scanCodebase {
		fmt.Println("✅ Compiled entire codebase context into mellow_prompt.md!")
	} else {
		fmt.Println("✅ Created mellow_prompt.md (Feed this file to your AI agent!)")
	}
}

func backupFile(filepathStr string) {
	if _, err := os.Stat(filepathStr); os.IsNotExist(err) {
		return
	}

	timestamp := time.Now().Format("20060102_150405")

	// Preserves original directory and file structures using real slashes
	backupPath := filepath.Join(historyDir, timestamp, filepathStr)
	backupDir := filepath.Dir(backupPath)

	_ = os.MkdirAll(backupDir, 0755)

	source, err := os.Open(filepathStr)
	if err != nil {
		return
	}
	defer source.Close()

	destination, err := os.Create(backupPath)
	if err != nil {
		return
	}
	defer destination.Close()

	_, _ = io.Copy(destination, source)
}

func ApplyChanges(containerPath string) {
	content, err := os.ReadFile(containerPath)
	if err != nil {
		logError(fmt.Sprintf("❌ Error: %s not found.", containerPath))
		return
	}

	lines := strings.Split(string(content), "\n")

	var currentFile string
	var searchContent, replaceContent []string
	var mode string
	changesApplied := 0

	for _, line := range lines {
		line = strings.TrimSuffix(line, "\r")

		if strings.HasPrefix(line, "[FILE]") {
			currentFile = strings.TrimSpace(strings.TrimPrefix(line, "[FILE]"))
		} else if strings.HasPrefix(line, "[SEARCH]") {
			mode = "SEARCH"
			searchContent = []string{}
		} else if strings.HasPrefix(line, "[REPLACE]") {
			mode = "REPLACE"
			replaceContent = []string{}
		} else if strings.HasPrefix(line, "[DELETE]") {
			mode = "DELETE"
			searchContent = []string{}
		} else if strings.HasPrefix(line, "[DELETE_FILE]") {
			mode = "DELETE_FILE"
		} else if strings.HasPrefix(line, "[CREATE]") {
			mode = "CREATE"
			replaceContent = []string{}
		} else if strings.HasPrefix(line, "[END]") {
			if currentFile != "" {
				success := executeChange(currentFile, searchContent, replaceContent, mode)
				if success {
					changesApplied++
				}
			}
			mode = ""
			searchContent = nil
			replaceContent = nil
		} else {
			if mode == "SEARCH" || mode == "DELETE" {
				searchContent = append(searchContent, line)
			} else if mode == "REPLACE" || mode == "CREATE" {
				replaceContent = append(replaceContent, line)
			}
		}
	}

	fmt.Printf("\n✅ Done! Successfully applied %d changes.\n", changesApplied)
}

func executeChange(filePath string, searchLines, replaceLines []string, mode string) bool {
	// Prevent accidental modification/execution of critical system or markdown files
	if isCriticalFile(filePath) {
		logError(fmt.Sprintf("⚠️  Blocked: Critical system or markdown file '%s' cannot be modified or executed via apply.", filePath))
		return false
	}

	dir := filepath.Dir(filePath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		logError(fmt.Sprintf("❌ Error creating directory %s: %v", dir, err))
		return false
	}

	if mode == "CREATE" {
		backupFile(filePath)
		replaceStr := strings.Join(replaceLines, "\n")
		err := os.WriteFile(filePath, []byte(replaceStr), 0644)
		if err != nil {
			logError(fmt.Sprintf("❌ Error creating file %s: %v", filePath, err))
			return false
		}
		fmt.Printf("✔️  Created file %s\n", filePath)
		return true
	}

	if mode == "DELETE_FILE" {
		if _, err := os.Stat(filePath); os.IsNotExist(err) {
			logError(fmt.Sprintf("❌ Error: File not found -> %s", filePath))
			return false
		}
		backupFile(filePath)
		err := os.Remove(filePath)
		if err != nil {
			logError(fmt.Sprintf("❌ Error deleting file %s: %v", filePath, err))
			return false
		}
		fmt.Printf("✔️  Deleted file %s\n", filePath)
		return true
	}

	if _, err := os.Stat(filePath); os.IsNotExist(err) {
		logError(fmt.Sprintf("❌ Error: File not found -> %s", filePath))
		return false
	}

	backupFile(filePath)

	contentBytes, _ := os.ReadFile(filePath)
	content := string(contentBytes)

	searchStr := strings.Join(searchLines, "\n")
	replaceStr := ""
	if mode == "REPLACE" {
		replaceStr = strings.Join(replaceLines, "\n")
	}

	if !strings.Contains(content, searchStr) && strings.Contains(content, strings.TrimRight(searchStr, "\n\r")) {
		searchStr = strings.TrimRight(searchStr, "\n\r")
		replaceStr = strings.TrimRight(replaceStr, "\n\r")
	}

	if strings.Contains(content, searchStr) {
		newContent := strings.Replace(content, searchStr, replaceStr, 1)
		err := os.WriteFile(filePath, []byte(newContent), 0644)
		if err != nil {
			logError(fmt.Sprintf("❌ Error writing file %s: %v", filePath, err))
			return false
		}

		action := "Replaced"
		if mode == "DELETE" {
			action = "Deleted"
		}
		fmt.Printf("✔️  %s snippet in %s\n", action, filePath)
		return true
	}

	logError(fmt.Sprintf("❌ Error: Could not find exact [SEARCH] string in %s", filePath))
	return false
}
