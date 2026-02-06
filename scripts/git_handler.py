import os
import subprocess
import logging
from datetime import datetime
import tempfile
import shutil
from pathlib import Path
import time
import stat


class GitHandler:
    def __init__(self, repo_path='.', log_file='git_operations.log'):
        """
        Initialize Git handler.

        Args:
            repo_path (str|Path): Path to Git repository
            log_file (str): Path to log file
        """
        self.repo_path = Path(repo_path)
        self.log_file = log_file

        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('git_handler')

    def _run_command(self, command):
        """
        Run a Git command and return result.

        Args:
            command (list): List of command arguments

        Returns:
            tuple: (exit_code, stdout, stderr)
        """
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.repo_path
            )
            stdout, stderr = process.communicate()
            return process.returncode, stdout.decode('utf-8'), stderr.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Error executing command {command}: {str(e)}")
            return 1, "", str(e)

    def push_changes(self, files=None, message=None):
        """
        Execute full cycle: add, commit, push.

        Args:
            files (list): List of files to add, None means all changes
            message (str): Commit message, defaults to timestamp

        Returns:
            bool: True if operation succeeded, False otherwise
        """
        try:
            # Add
            add_command = ['git', 'add'] + (files if files else ['.'])
            code, stdout, stderr = self._run_command(add_command)
            if code != 0:
                self.logger.error(f"Error during git add: {stderr}")
                return False

            # Check status before commit
            status_command = ['git', 'status', '--porcelain']
            code, stdout, stderr = self._run_command(status_command)
            if not stdout.strip():
                self.logger.info("No changes to commit")
                return True

            # Commit
            if message is None:
                message = f"Update sentiment data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

            # Ensure git is configured
            name_cmd = ['git', 'config', '--get', 'user.name']
            email_cmd = ['git', 'config', '--get', 'user.email']

            _, name, _ = self._run_command(name_cmd)
            _, email, _ = self._run_command(email_cmd)

            if not name.strip() or not email.strip():
                self.logger.error("Git user.name or user.email not configured")
                # Set temporary configuration
                self._run_command(['git', 'config', 'user.name', 'Sentiment Bot'])
                self._run_command(['git', 'config', 'user.email', 'sentiment.bot@example.com'])

            commit_command = ['git', 'commit', '-m', message]
            code, stdout, stderr = self._run_command(commit_command)

            if code != 0:
                if "nothing to commit" in stderr:
                    self.logger.info("Nothing to commit")
                    return True
                self.logger.error(f"Error during git commit. Code: {code}, Stdout: {stdout}, Stderr: {stderr}")
                return False

            # Push
            push_command = ['git', 'push']
            code, stdout, stderr = self._run_command(push_command)
            if code != 0:
                # If error is about missing upstream branch
                if "no upstream branch" in stderr:
                    self.logger.info("Attempting to set upstream branch...")
                    push_command = ['git', 'push', '--set-upstream', 'origin', 'master']
                    code, stdout, stderr = self._run_command(push_command)

                if code != 0:
                    self.logger.error(f"Error during git push. Code: {code}, Stdout: {stdout}, Stderr: {stderr}")
                    return False

            self.logger.info("Successfully pushed changes to repository")
            return True

        except Exception as e:
            self.logger.error(f"Error during git operations: {str(e)}")
            return False

    def push(self, remote='origin', branch='master'):
        """
        Push changes to remote repository.

        Args:
            remote (str): Name of remote repository
            branch (str): Name of branch

        Returns:
            bool: True if operation succeeded, False otherwise
        """
        # First try standard push
        command = ['git', 'push', remote, branch]
        code, stdout, stderr = self._run_command(command)

        # If error is about missing upstream branch
        if code != 0 and "no upstream branch" in stderr:
            # Try push with setting upstream
            command = ['git', 'push', '--set-upstream', remote, branch]
            code, stdout, stderr = self._run_command(command)

        if code != 0:
            self.logger.error(f"Error during git push: {stderr}")
            return False

        self.logger.info(f"Successfully pushed changes to {remote}/{branch}")
        return True


class GitPublisher:
    def __init__(self, source_dir, public_repo_url, target_dir='data'):
        """
        Initialize GitPublisher to publish CSV files to a public repository.

        Args:
            source_dir (str): Directory containing CSV files to publish
            public_repo_url (str): URL of the public repository
            target_dir (str): Target directory in the public repository
        """
        self.source_dir = Path(source_dir)
        self.public_repo_url = public_repo_url
        self.target_dir = target_dir
        self.temp_dir = None

    def _remove_readonly(self, func, path, excinfo):
        """Helper function to remove read-only files"""
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception as e:
            logging.warning(f"Cannot remove {path}: {e}")

    def _safe_cleanup(self):
        """Safely clean up temporary directory"""
        if self.temp_dir and Path(self.temp_dir).exists():
            try:
                # Change permissions on all files
                for root, dirs, files in os.walk(self.temp_dir):
                    for d in dirs:
                        os.chmod(os.path.join(root, d), stat.S_IWRITE)
                    for f in files:
                        os.chmod(os.path.join(root, f), stat.S_IWRITE)

                # Try to remove directory
                shutil.rmtree(self.temp_dir, onerror=self._remove_readonly)

                # If directory still exists, wait and try again
                if Path(self.temp_dir).exists():
                    time.sleep(1)  # Give system time to release files
                    shutil.rmtree(self.temp_dir, onerror=self._remove_readonly)

                logging.info(f"Cleaned up temporary directory: {self.temp_dir}")
            except Exception as e:
                logging.warning(f"Cannot clean up temporary directory {self.temp_dir}: {e}")

    def publish(self):
        """
        Publish CSV files to the public repository.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create a temporary directory
            self.temp_dir = tempfile.mkdtemp()
            logging.info(f"Created temporary directory: {self.temp_dir}")

            # Clone the public repository
            logging.info(f"Cloning repository: {self.public_repo_url}")
            result = subprocess.run(
                ['git', 'clone', self.public_repo_url, self.temp_dir],
                capture_output=True, text=True
            )

            if result.returncode != 0:
                logging.error(f"Failed to clone repository: {result.stderr}")
                return False

            # Create target directory if it doesn't exist
            target_path = Path(self.temp_dir) / self.target_dir
            target_path.mkdir(exist_ok=True)

            # Copy CSV files from source directory to target directory
            csv_files = list(self.source_dir.glob('*.csv'))
            logging.info(f"Found {len(csv_files)} CSV files to publish")

            for csv_file in csv_files:
                shutil.copy2(csv_file, target_path / csv_file.name)
                logging.info(f"Copied {csv_file.name} to {target_path}")

            # Change to the repository directory
            os.chdir(self.temp_dir)

            # Add all changes
            subprocess.run(['git', 'add', f"{self.target_dir}/*.csv"], check=True)

            # Commit changes
            commit_message = "Update sentiment data CSV files"
            result = subprocess.run(
                ['git', 'commit', '-m', commit_message],
                capture_output=True, text=True
            )

            # Check if there were changes to commit
            if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
                logging.info("No changes to commit to public repository")
                return True

            # Push changes
            subprocess.run(['git', 'push'], check=True)

            logging.info("Successfully pushed CSV files to public repository")
            return True

        except Exception as e:
            logging.error(f"Error publishing to public repository: {e}")
            return False

        finally:
            # Use safe cleanup
            self._safe_cleanup()
