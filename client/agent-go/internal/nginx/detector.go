package nginx

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
)

// CertPath represents a detected SSL certificate path from nginx config
type CertPath struct {
	LocalPath  string // e.g. /etc/nginx/ssl/api.example.com.crt
	ServerName string // from server_name directive, used as cert_name
}

// NginxProcess represents a running nginx master process
type NginxProcess struct {
	PID      int
	PPID     int
	User     string
	CmdLine  string
	ConfPath string // nginx config path
}

// DetectCertPaths automatically detects all SSL certificate paths from running nginx instances
func DetectCertPaths() ([]CertPath, error) {
	// 1. Find all nginx master processes
	masters, err := GetNginxMasterProcesses()
	if err != nil {
		return nil, fmt.Errorf("failed to get nginx master processes: %w", err)
	}

	if len(masters) == 0 {
		return nil, fmt.Errorf("no nginx master process found")
	}

	// 2. For each master, parse config and extract cert paths
	seen := make(map[string]bool) // deduplicate by local_path
	var results []CertPath

	for _, master := range masters {
		paths, err := parseNginxConfigForCerts(master.ConfPath)
		if err != nil {
			// Log warning but continue with other masters
			continue
		}
		for _, p := range paths {
			if !seen[p.LocalPath] {
				seen[p.LocalPath] = true
				results = append(results, p)
			}
		}
	}

	return results, nil
}

// GetNginxMasterProcesses finds all nginx master processes
func GetNginxMasterProcesses() ([]NginxProcess, error) {
	// Use ps to find nginx master processes
	// Try different ps formats for compatibility (Alpine busybox vs standard ps)
	var output []byte
	var err error

	// First try: busybox/alpine format
	cmd := exec.Command("ps", "-o", "pid,ppid,user,args")
	output, err = cmd.Output()
	if err != nil {
		// Fallback: standard ps format
		cmd = exec.Command("ps", "-eo", "pid,ppid,user,cmd")
		output, err = cmd.Output()
		if err != nil {
			return nil, fmt.Errorf("failed to run ps: %w", err)
		}
	}

	var masters []NginxProcess
	scanner := bufio.NewScanner(strings.NewReader(string(output)))

	for scanner.Scan() {
		line := scanner.Text()
		// Look for nginx master process
		// Pattern: "nginx: master process /path/to/nginx -c /path/to/conf"
		if !strings.Contains(line, "nginx: master") {
			continue
		}

		proc, err := parsePSLine(line)
		if err != nil {
			continue
		}

		// Extract config path from command line
		proc.ConfPath = extractConfigPath(proc.CmdLine)
		if proc.ConfPath == "" {
			// Default config path
			proc.ConfPath = "/etc/nginx/nginx.conf"
		}

		masters = append(masters, proc)
	}

	return masters, nil
}

// parsePSLine parses a line from ps output
// Format: PID PPID USER CMD
func parsePSLine(line string) (NginxProcess, error) {
	// ps output has fixed-width columns, we need to parse carefully
	// Example: "   123     1 root   nginx: master process /usr/sbin/nginx -c /etc/nginx/nginx.conf"

	fields := strings.Fields(line)
	if len(fields) < 4 {
		return NginxProcess{}, fmt.Errorf("invalid ps line: %s", line)
	}

	var proc NginxProcess
	if _, err := fmt.Sscanf(fields[0], "%d", &proc.PID); err != nil {
		return NginxProcess{}, err
	}
	if _, err := fmt.Sscanf(fields[1], "%d", &proc.PPID); err != nil {
		return NginxProcess{}, err
	}
	proc.User = fields[2]
	// CmdLine is everything after user
	proc.CmdLine = strings.Join(fields[3:], " ")

	return proc, nil
}

// extractConfigPath extracts -c argument from nginx command line
func extractConfigPath(cmdLine string) string {
	// Pattern: -c /path/to/conf
	re := regexp.MustCompile(`-c\s+(\S+)`)
	matches := re.FindStringSubmatch(cmdLine)
	if len(matches) > 1 {
		return matches[1]
	}
	return ""
}

// parseNginxConfigForCerts parses nginx config and extracts ssl_certificate paths
func parseNginxConfigForCerts(configPath string) ([]CertPath, error) {
	// First, resolve the main config
	absPath, err := filepath.Abs(configPath)
	if err != nil {
		return nil, err
	}

	// Track visited files to avoid infinite loops
	visited := make(map[string]bool)
	var results []CertPath

	// Parse recursively
	results, err = parseConfigFile(absPath, visited)
	if err != nil {
		return nil, err
	}

	return results, nil
}

// parseConfigFile parses a single nginx config file and its includes
func parseConfigFile(path string, visited map[string]bool) ([]CertPath, error) {
	absPath, err := filepath.Abs(path)
	if err != nil {
		return nil, err
	}

	// Avoid parsing the same file twice
	if visited[absPath] {
		return nil, nil
	}
	visited[absPath] = true

	data, err := os.ReadFile(absPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file %s: %w", absPath, err)
	}

	var results []CertPath
	content := string(data)

	// Get the base directory for resolving relative paths
	baseDir := filepath.Dir(absPath)

	// Extract ssl_certificate directives (pass baseDir for relative path resolution)
	results = append(results, extractSSLCerts(content, baseDir)...)

	// Extract and process include directives
	includes := extractIncludes(content)

	for _, include := range includes {
		// Handle glob patterns and relative paths
		matches, err := filepath.Glob(filepath.Join(baseDir, include))
		if err != nil {
			continue
		}

		for _, match := range matches {
			paths, err := parseConfigFile(match, visited)
			if err != nil {
				continue
			}
			results = append(results, paths...)
		}
	}

	return results, nil
}

// extractSSLCerts extracts ssl_certificate paths from config content
// baseDir is used to resolve relative paths to absolute paths
func extractSSLCerts(content string, baseDir string) []CertPath {
	var results []CertPath

	// Pattern: ssl_certificate /path/to/cert.crt;
	re := regexp.MustCompile(`ssl_certificate\s+([^;]+);`)
	matches := re.FindAllStringSubmatch(content, -1)

	// Also extract server_name to use as cert_name
	serverNameRe := regexp.MustCompile(`server_name\s+([^;]+);`)
	serverNames := serverNameRe.FindAllStringSubmatch(content, -1)

	// Get first server_name if available
	serverName := ""
	if len(serverNames) > 0 {
		names := strings.Fields(serverNames[0][1])
		if len(names) > 0 {
			serverName = names[0] // Use the first server_name
		}
	}

	for _, match := range matches {
		certPath := strings.TrimSpace(match[1])
		// Skip variables and invalid paths
		if strings.HasPrefix(certPath, "$") || certPath == "" {
			continue
		}

		// Resolve relative path to absolute path
		absCertPath := certPath
		if !filepath.IsAbs(certPath) {
			absCertPath = filepath.Join(baseDir, certPath)
		}

		results = append(results, CertPath{
			LocalPath:  absCertPath,
			ServerName: serverName,
		})
	}

	return results
}

// extractIncludes extracts include paths from config content
func extractIncludes(content string) []string {
	var results []string

	// Pattern: include /path/to/*.conf;
	re := regexp.MustCompile(`include\s+([^;]+);`)
	matches := re.FindAllStringSubmatch(content, -1)

	for _, match := range matches {
		includePath := strings.TrimSpace(match[1])
		// Skip mime.types and other non-config includes
		if strings.HasSuffix(includePath, ".types") {
			continue
		}
		results = append(results, includePath)
	}

	return results
}
