import os
import configparser # parses microsoft INI file format



class Repository():

    # force is used to create a new repository from a repository object
    def __init__(self, path, force=False):
        # this is where the files checked into the version control live
        self.worktree = path
        # this is where git stores all its data, typically worktree/.git
        self.gitdir = os.path.join(path, ".git")

        if not (force or os.path.exists(self.gitdir)):
            raise Exception(f"Not a git repository {path}")
        
        # the git conf --> an INI file
        self.conf = configparser.ConfigParser()
        config_file_path = get_path_to_repo_file(self, "config")

        if config_file_path and os.path.exists(config_file_path):
            self.conf.read([config_file_path])
        elif not force:
            raise Exception("Configuration file missing")
        
        if not force:
            version = int(self.conf.get("core", "repositoryformatversion"))
            if version != 0:
                raise Exception(f"Unsupported repositoryformatversion {version}")


def get_path_under_repo(repo: Repository, *path):
    """
    Util function to get path under the git directory
    """
    return os.path.join(repo.gitdir, *path)

def get_path_to_repo_file(repo: Repository, *path, mkdir=False):
    """
    * Util function to get or create the path to a file
    * Raise exception if directory name for the file is already used by another file
    """
    # check for existence of or create parent directory
    if get_path_to_repo_dir(repo, *path[:-1], mkdir=mkdir):
        return get_path_under_repo(repo, *path)

def get_path_to_repo_dir(repo: Repository, *path, mkdir=False):
    """
    * Util function to get or create the path to a directory under the git directory. 
    * Raise exception if path is not a directory
    """
    path = get_path_under_repo(repo, *path)

    if os.path.exists(path):
        if os.path.isdir(path):
            return path
        else:
            raise Exception(f"Not a directory {path}")
    
    if mkdir:
        os.makedirs(path)
        return path

def repo_default_config():
    ret = configparser.ConfigParser()

    ret.add_section("core")

    # version of the gitdir format. 0 means initial, 1 is the same with some extensions. git panics on > 1
    ret.set("core", "repositoryformatversion", "0")
    # disable tracking of file modes (permissions) changes in the worktree
    ret.set("core", "filemode", "false")
    # indicates that this repository has a worktree. git supports an additional `worktree` key which indicates 
    # its location if not `..`
    ret.set("core", "bare", "false")

    return ret

def create_repo(path):
    """
    Create a git repository inside the specified directory
    """
    repo = Repository(path, force=True)

    if os.path.exists(repo.worktree):
        if not os.path.isdir(repo.worktree):
            raise Exception(f"{repo.worktree} is not a directory!")
        if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
            raise Exception(f"{path} already has a gitdir!")
    else:
        os.makedirs(repo.worktree)

    # create essential directories
    assert get_path_to_repo_dir(repo, "branches", mkdir=True)
    assert get_path_to_repo_dir(repo, "refs", "tags", mkdir=True)
    assert get_path_to_repo_dir(repo, "refs", "heads", mkdir=True)
    assert get_path_to_repo_dir(repo, "objects", mkdir=True)

    # create essential files

    # free form description for humans to read, rarely used
    with open(get_path_to_repo_file(repo, "description"), 'w') as fp:
        fp.write("Unnamed repository; edit this file 'description' to name the repository.\n")
    
    # reference to the current head
    with open(get_path_to_repo_file(repo, "HEAD"), 'w') as fp:
        fp.write("ref: refs/heads/master\n")
    
    # gitconfig
    with open(get_path_to_repo_file(repo, "config"), 'w') as fp:
        config = repo_default_config()
        config.write(fp)
        repo.conf = config
