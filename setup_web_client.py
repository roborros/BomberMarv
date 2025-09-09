#!/usr/bin/env python3
"""
Setup script for BomberMarv web client
Installs Node.js dependencies and builds the React frontend
"""
import subprocess
import sys
import os
from pathlib import Path

def run_command(command, cwd=None):
    """Run a command and return success status"""
    try:
        print(f"Running: {command}")
        result = subprocess.run(command, shell=True, cwd=cwd, check=True, 
                              capture_output=True, text=True)
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        print(f"Output: {e.stdout}")
        print(f"Error: {e.stderr}")
        return False

def check_node_installed():
    """Check if Node.js is installed"""
    try:
        result = subprocess.run(['node', '--version'], capture_output=True, text=True)
        version = result.stdout.strip()
        print(f"Node.js version: {version}")
        
        result = subprocess.run(['npm', '--version'], capture_output=True, text=True)
        version = result.stdout.strip()
        print(f"npm version: {version}")
        return True
    except FileNotFoundError:
        return False

def setup_web_client():
    """Set up the web client"""
    web_client_dir = Path("web_client")
    
    if not web_client_dir.exists():
        print("Error: web_client directory not found!")
        return False
    
    print("Setting up BomberMarv web client...")
    
    # Check Node.js installation
    if not check_node_installed():
        print("Error: Node.js is not installed!")
        print("Please install Node.js from https://nodejs.org/")
        print("Minimum version: 14.x")
        return False
    
    # Install dependencies
    print("\nInstalling dependencies...")
    if not run_command("npm install", cwd=web_client_dir):
        print("Failed to install dependencies!")
        return False
    
    # Build the project
    print("\nBuilding the project...")
    if not run_command("npm run build", cwd=web_client_dir):
        print("Failed to build the project!")
        return False
    
    print("\n[OK] Web client setup complete!")
    print("\nTo start the game with web support:")
    print("  python pyBomberMarv_dual.py")
    print("\nTo start development server:")
    print("  cd web_client && npm run dev")
    print("\nWeb client will be available at:")
    print("  - Development: http://localhost:3000")
    print("  - Production: http://localhost:8080")
    
    return True

def main():
    """Main entry point"""
    print("BomberMarv Web Client Setup")
    print("=" * 40)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--dev-only":
        print("Installing dependencies only (no build)...")
        web_client_dir = Path("web_client")
        if run_command("npm install", cwd=web_client_dir):
            print("[OK] Dependencies installed!")
            print("Run 'npm run dev' in web_client/ to start development server")
        return
    
    success = setup_web_client()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()