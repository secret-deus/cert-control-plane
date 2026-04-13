package main

import (
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"go.uber.org/zap"

	"github.com/cert-control-plane/agent-go/internal/config"
	"github.com/cert-control-plane/agent-go/internal/nginx"
	"github.com/cert-control-plane/agent-go/internal/runner"
)

func main() {
	var configPath string
	flag.StringVar(&configPath, "config", "", "Path to configuration file")
	flag.Parse()

	// Initialize logger
	logger, err := zap.NewProduction()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to create logger: %v\n", err)
		os.Exit(1)
	}
	defer logger.Sync()

	// Load configuration
	cfg, err := config.Load(configPath)
	if err != nil {
		logger.Fatal("Failed to load configuration", zap.Error(err))
	}

	// Auto-detect nginx cert paths if enabled and cert_table is empty
	if cfg.AutoDetect && len(cfg.CertTable) == 0 {
		logger.Info("Auto-detecting nginx SSL certificate paths...")
		paths, err := nginx.DetectCertPaths()
		if err != nil {
			logger.Warn("Auto-detect failed, continuing with empty cert_table",
				zap.Error(err))
		} else {
			logger.Info("Detected certificate paths", zap.Int("count", len(paths)))
			for _, p := range paths {
				cfg.CertTable = append(cfg.CertTable, config.CertTableEntry{
					LocalPath: p.LocalPath,
					CertName:  p.ServerName,
				})
				logger.Info("  - detected cert",
					zap.String("path", p.LocalPath),
					zap.String("server_name", p.ServerName))
			}
		}
	}

	// Create runner
	r := runner.New(cfg, logger)

	// Handle graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		<-sigChan
		logger.Info("Shutting down...")
		os.Exit(0)
	}()

	// Run agent
	if err := r.Run(); err != nil {
		logger.Fatal("Agent failed", zap.Error(err))
	}
}
