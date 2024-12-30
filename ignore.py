from objects import get_path_to_repo_file, object_read
import os
from index import index_read
from fnmatch import fnmatch

class Ignore():
    """
    There are 2 types of ignore files:
    1. Some live in the index --> There is usually only 1 ignore file in the root directory, there can be
        one in each directory, which applies to that directory and its subdirectories. The patterns in
        the subdirectory take precedence over root.
    2. Others live outside the index --> Global ignore file (~/.config/git/ignore) and repo specific
        (.git/info/exclude). Applied everywhere, but at a lower priority.
    """

    def __init__(self, absolute=None, scoped=None):
        self.absolute = absolute if absolute else list()
        self.scoped = scoped if scoped else dict()

def gitignore_parse_pattern(raw):
    raw = raw.strip()

    if not raw or raw[0] == '#':
        return
    elif raw[0] == '!':
        return raw[1:], False
    elif raw[0] == '\\':
        return raw[1:], True
    return raw, True

def gitignore_parse(lines):
    """
    Using lines instead of parsing files because we may need to read rules from git blobs as well.
    """
    rules = list()

    for line in lines:
        rule = gitignore_parse_pattern(line)
        if rule:
            rules.append(rule)
    
    return rules

def gitignore_read(repo):
    ignore = Ignore()

    # read local config in .git/info/exclude
    local_config = get_path_to_repo_file(repo, "info", "exclude")
    if os.path.exists(local_config):
        with open(local_config, "r") as fp:
            ignore.absolute.append(gitignore_parse(fp.readlines()))
    
    # global config
    if "XDG_CONFIG_HOME" in os.environ:
        config_home = os.environ["XDG_CONFIG_HOME"]
    else:
        config_home = os.path.expanduser("~/.config")
    global_config = os.path.join(config_home, "git", "ignore")

    if os.path.exists(global_config):
        with open(global_config, "r") as fp:
            ignore.absolute.append(gitignore_parse(fp.readlines()))
    
    # scoped .gitignore files in the index
    # reading these from the index instead of the worktree, since staged .gitignore files also matter,
    # not just committed ones.
    index = index_read(repo)

    for entry in index.entries:
        if entry.name == '.gitignore' or entry.name.endswith("/.gitignore"):
            dir_name = os.path.dirname(entry.name)
            contents = object_read(repo, entry.sha)
            lines = contents.blobdata.decode('utf-8').splitlines()
            ignore.scoped[dir_name] = gitignore_parse(lines)
    
    return ignore

def check_ignore_path_given_rules(rules, path):
    result = None

    for pattern, value in rules:
        if fnmatch(path, pattern):
            # not returning value here, since rules are processed in order, and multiple rules can be 
            # applicable to a single file.
            # the last one wins
            result = value
    
    return result

def check_ignore_scoped(scoped_rules, path):
    parent = os.path.dirname(path)
    while True:
        if parent in scoped_rules:
            result = check_ignore_path_given_rules(scoped_rules[parent], path)
            if result:
                return result
        if parent == "":
            break
        parent = os.path.dirname(parent)

def check_ignore_absolute(absolute_rules, path):
    for rule in absolute_rules:
        result = check_ignore_path_given_rules(rule, path)
        if result:
            return result
    return False

def check_ignore(ignore, path):
    if os.path.isabs(path):
        raise Exception("This function requires path to be relative to the repository's root")
    
    result = check_ignore_scoped(ignore.scoped, path)
    if result:
        return result
    
    return check_ignore_absolute(ignore.absolute, path)