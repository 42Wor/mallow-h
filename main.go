package main

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const historyDir = ".mellow/history"

func main() {
	args := os.Args[1:]
	if len(args) == 0 || args[0] == "help" {
		printHelp()
		return
	}

	if args[0] == "init" {
		initMellow()
		return
	}

	if args[0] == "apply" {
		containerFile := "container.txt"
		if len(args) > 1 {
			containerFile = args[1]
		}
		applyChanges(containerFile)
		return
	}

	fmt.Println("❌ Unknown command. Run 'mellow help' for usage.")
}

func printHelp() {
	fmt.Println("🚀 Mellow CLI - LLM Code Harness")
	fmt.Println("Usage:")
	fmt.Println("  mellow init               - Initialize the .mellow history folder, container.txt, and mellow_prompt.md")
	fmt.Println("  mellow apply [file.txt]   - Apply changes from container.txt (defaults to container.txt)")
}

func initMellow() {
	err := os.MkdirAll(historyDir, 0755)
	if err != nil {
		fmt.Printf("❌ Failed to create %s: %v\n", historyDir, err)
		return
	}

	// Create empty container.txt if it doesn't exist
	if _, err := os.Stat("container.txt"); os.IsNotExist(err) {
		err = os.WriteFile("container.txt", []byte(""), 0644)
		if err != nil {
			fmt.Printf("❌ Failed to create container.txt: %v\n", err)
			return
		}
	}

	// Create the AI prompt instructions file
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

### 3. To Delete Code
[FILE] path/to/existing_file.ext
[DELETE]
<exact lines of code to remove>
[END]

## Important Constraints:
1. The [SEARCH] block must match the existing code *exactly*, including indentation and spacing.
2. Include enough context in the [SEARCH] block so it is unique within the file.
3. Do not use markdown code blocks ("` + "```" + `") around the format. Just output the raw text.
4. You can output multiple blocks for multiple files or multiple changes in the same file.`

	if _, err := os.Stat("mellow_prompt.md"); os.IsNotExist(err) {
		err = os.WriteFile("mellow_prompt.md", []byte(promptContent), 0644)
		if err != nil {
			fmt.Printf("❌ Failed to create mellow_prompt.md: %v\n", err)
			return
		}
	}

	fmt.Println("✅ Initialized .mellow history folder.")
	fmt.Println("✅ Created container.txt")
	fmt.Println("✅ Created mellow_prompt.md (Feed this file to your AI agent!)")
}

func backupFile(filepathStr string) {
	if _, err := os.Stat(filepathStr); os.IsNotExist(err) {
		return // Nothing to backup
	}

	timestamp := time.Now().Format("20060102_150405")
	backupName := fmt.Sprintf("%s_%s", timestamp, filepath.Base(filepathStr))
	backupPath := filepath.Join(historyDir, backupName)

	_ = os.MkdirAll(historyDir, 0755)

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

func applyChanges(containerPath string) {
	content, err := os.ReadFile(containerPath)
	if err != nil {
		fmt.Printf("❌ Error: %s not found.\n", containerPath)
		return
	}

	lines := strings.Split(string(content), "\n")

	var currentFile string
	var searchContent, replaceContent []string
	var mode string
	changesApplied := 0

	for _, line := range lines {
		// Clean up any carriage return chars from Windows formatting
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
	// Ensure directory exists
	dir := filepath.Dir(filePath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		fmt.Printf("❌ Error creating directory %s: %v\n", dir, err)
		return false
	}

	// Handle CREATE mode
	if mode == "CREATE" {
		backupFile(filePath)
		replaceStr := strings.Join(replaceLines, "\n")
		err := os.WriteFile(filePath, []byte(replaceStr), 0644)
		if err != nil {
			fmt.Printf("❌ Error creating file %s: %v\n", filePath, err)
			return false
		}
		fmt.Printf("✔️  Created file %s\n", filePath)
		return true
	}

	// Handle SEARCH/REPLACE and DELETE modes
	if _, err := os.Stat(filePath); os.IsNotExist(err) {
		fmt.Printf("❌ Error: File not found -> %s\n", filePath)
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

	// Fallback for trailing newline issues
	if !strings.Contains(content, searchStr) && strings.Contains(content, strings.TrimRight(searchStr, "\n\r")) {
		searchStr = strings.TrimRight(searchStr, "\n\r")
		replaceStr = strings.TrimRight(replaceStr, "\n\r")
	}

	if strings.Contains(content, searchStr) {
		newContent := strings.Replace(content, searchStr, replaceStr, 1)
		err := os.WriteFile(filePath, []byte(newContent), 0644)
		if err != nil {
			fmt.Printf("❌ Error writing file %s: %v\n", filePath, err)
			return false
		}

		action := "Replaced"
		if mode == "DELETE" {
			action = "Deleted"
		}
		fmt.Printf("✔️  %s snippet in %s\n", action, filePath)
		return true
	}

	fmt.Printf("❌ Error: Could not find exact [SEARCH] string in %s\n", filePath)
	return false
}
