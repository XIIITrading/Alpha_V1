#!/usr/bin/env python3
"""
Git Commit and Push Script
Automates the git add, commit, and push process with user input for commit message.
"""

import subprocess
import sys
import os

def run_command(command, description):
    """Run a shell command and handle errors."""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        if result.stdout.strip():
            print(f"Output: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error during {description}: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr}")
        return False

def main():
    print("🚀 Git Commit and Push Script")
    print("=" * 40)
    
    # Check if we're in a git repository
    if not os.path.exists('.git'):
        print("❌ Error: Not in a git repository. Please run this script from your project root.")
        sys.exit(1)
    
    # Get commit message from user
    print("\n💬 Enter your commit message:")
    commit_message = input("> ").strip()
    
    if not commit_message:
        print("❌ Error: Commit message cannot be empty.")
        sys.exit(1)
    
    print(f"\n📝 Commit message: '{commit_message}'")
    
    # Confirm with user
    confirm = input("\n🤔 Proceed with commit and push? (y/N): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("❌ Operation cancelled.")
        sys.exit(0)
    
    print("\n" + "=" * 40)
    
    # Execute git commands
    commands = [
        ("git add .", "Adding all files to staging"),
        (f'git commit -m "{commit_message}"', "Creating commit"),
        ("git push", "Pushing to remote repository")
    ]
    
    for command, description in commands:
        if not run_command(command, description):
            print(f"\n❌ Failed at: {description}")
            print("💡 You may need to check your git status or remote configuration.")
            sys.exit(1)
    
    print("\n" + "=" * 40)
    print("🎉 Success! All changes have been committed and pushed to GitHub.")
    print(f"📋 Commit message: '{commit_message}'")

if __name__ == "__main__":
    main() 