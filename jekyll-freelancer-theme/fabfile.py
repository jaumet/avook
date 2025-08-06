from fabric import task, Connection
from invoke import run  # Import `run` for local shell commands
import os

REMOTE_HOST = "phab"
REMOTE_PATH = "/server/audiovook.com/www/html"

@task
def build(c):
    """Build the Jekyll site locally."""
    print("Building the site...")
    run('bundle exec jekyll build')  # Use `run` to execute local commands

@task
def deploy(c):
    """Deploy the site to the server."""
    print("Deploying to the server...")
    build(c)  # Build the site first

    # Create a connection
    conn = Connection(REMOTE_HOST)

    # Upload entire directory
    print(f"Uploading site to {REMOTE_PATH}...")
    conn.run(f'mkdir -p {REMOTE_PATH}')  # Ensure the remote directory exists
    for root, dirs, files in os.walk('_site'):
        for file in files:
            local_path = os.path.join(root, file)
            remote_path = os.path.join(REMOTE_PATH, os.path.relpath(local_path, '_site'))
            conn.run(f'mkdir -p {os.path.dirname(remote_path)}')  # Ensure remote directories exist
            conn.put(local_path, remote_path)

