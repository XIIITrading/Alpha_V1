import os
from pathlib import Path
import datetime

def should_ignore(path):
    """Check if the path should be ignored."""
    ignore_patterns = {
        '.git', '__pycache__', '.pytest_cache', '.venv', 'venv', 
        'node_modules', '.idea', '.vscode', '*.pyc', '*.pyo', 
        '*.pyd', '.DS_Store', '*.so', '*.dylib', '*.dll'
    }
    return any(pattern in str(path) for pattern in ignore_patterns)

def get_file_description(file_path):
    """Get a description for the file based on its name and content."""
    descriptions = {
        'README.md': 'Project documentation',
        'requirements.txt': 'Python dependencies',
        'config.py': 'Configuration settings',
        'main.py': 'Main application entry point',
        '__init__.py': '',
        'settings.py': 'Global settings',
        'BACKEND_QUICKSTART.md': 'Backend setup and usage guide',
        'start_backend.bat': 'Windows batch script to start backend',
        'start_backend.py': 'Python script to start backend',
    }
    return descriptions.get(file_path.name, '')

def generate_tree(startpath, output_file):
    """Generate a tree structure and write it to a file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        # Write header
        f.write(f"# Project Structure\n")
        f.write(f"Last updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("```\n")
        
        # Write root
        root_name = os.path.basename(str(startpath))
        f.write(f"{root_name}/\n")
        
        # Generate tree
        for root, dirs, files in os.walk(str(startpath)):
            # Skip ignored directories
            dirs[:] = [d for d in dirs if not should_ignore(d)]
            
            level = root.replace(str(startpath), '').count(os.sep)
            indent = '│   ' * level
            
            # Write directory
            if level > 0:
                dir_name = os.path.basename(root)
                f.write(f"{indent}├── {dir_name}/\n")
            
            # Write files
            sub_indent = '│   ' * (level + 1)
            for file in sorted(files):
                if not should_ignore(file):
                    description = get_file_description(Path(file))
                    desc_str = f" # {description}" if description else ""
                    f.write(f"{sub_indent}├── {file}{desc_str}\n")
        
        f.write("```\n")

def main():
    # Get the project root directory (two levels up from this script)
    project_root = Path(__file__).parent.parent.absolute()
    output_file = Path(__file__).parent / 'tree_structure.md'
    
    print(f"Generating tree structure for: {project_root}")
    print(f"Output file: {output_file}")
    
    generate_tree(project_root, output_file)
    print("Tree structure has been updated successfully!")

if __name__ == "__main__":
    main() 