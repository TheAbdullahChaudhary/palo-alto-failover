#!/usr/bin/env python3
"""
Lambda packaging utility for CDK deployment
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

def package_lambda_layer():
    """Package Python dependencies into a Lambda layer"""
    print("Packaging Lambda layer...")
    
    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        layer_dir = Path(temp_dir) / "python"
        layer_dir.mkdir(parents=True)
        
        # Install dependencies using poetry
        subprocess.run([
            "poetry", "export", "--without-hashes", "--format=requirements.txt", 
            "--output", str(Path(temp_dir) / "requirements.txt")
        ], check=True)
        
        subprocess.run([
            "pip", "install", "-r", str(Path(temp_dir) / "requirements.txt"),
            "-t", str(layer_dir)
        ], check=True)
        
        # Create layer zip
        layer_zip = Path("../lambda_layer.zip")
        shutil.make_archive(str(layer_zip.with_suffix("")), "zip", temp_dir)
        
    print(f"Lambda layer packaged: {layer_zip}")
    return layer_zip

def package_lambda_functions():
    """Package Lambda function source code"""
    print("Packaging Lambda functions...")
    
    functions_dir = Path("../lambda_functions")
    package_zip = Path("../lambda_functions.zip")
    
    # Create zip with lambda functions
    shutil.make_archive(
        str(package_zip.with_suffix("")), 
        "zip", 
        functions_dir.parent,
        functions_dir.name
    )
    
    print(f"Lambda functions packaged: {package_zip}")
    return package_zip

if __name__ == "__main__":
    package_lambda_layer()
    package_lambda_functions()
