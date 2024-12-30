import argparse, os, sys
from repository import *
import pwd, grp
from objects import *
from index import *
from ignore import gitignore_read, check_ignore

def cmd_init(args):
    create_repo(args.path)

def cmd_cat_file(args):
    repo = get_repo_for_path()
    cat_file(repo, args.object, args.type.encode()) 

def cat_file(repo, obj, type=None):
    obj = object_read(repo, object_find(repo, obj, type))
    sys.stdout.buffer.write(obj.serialize())

def cmd_hash_object(args):
    """
    We only implement object storage using "loose objects". Git also has another storage mechanism
    called packfiles, which is essentially just a collection of multiple loose objects.
    https://wyag.thb.lt/#packfiles
    """
    if args.write:
        repo = get_repo_for_path()
    else:
        repo = None
    
    with open(args.path, 'rb') as fp:
        sha = object_hash(fp, args.type.encode(), repo)
        print(sha)

def cmd_log(sha):
    repo = get_repo_for_path()

    print("digraph wyaglog{")
    print("  node[shape=rect]")
    log_graphviz(repo, object_find(repo, sha), set())
    print("}")

def cmd_ls_tree(args):
    repo = get_repo_for_path()
    ls_tree(repo, args.tree, args.recursive)

def cmd_checkout(args):
    repo = get_repo_for_path()
    obj = object_read(repo, object_find(repo, args.commit))

    # if the object is a commit, we grab its tree
    if obj.object_type == b'commit':
        obj = object_read(repo, obj.kvlm[b'tree'].decode('ascii'))
    
    # verify that the path is an empty directory
    if os.path.exists(args.path):
        if not os.path.isdir(args.path):
            raise Exception(f"Not a directory {args.path}!")
        if os.listdir(args.path):
            raise Exception(f"Not empty {args.path}!")
    else:
        os.makedirs(args.path)
    
    tree_checkout(repo, obj, os.path.realpath(args.path))

def cmd_show_ref(args):
    repo = get_repo_for_path()
    refs = ref_list(repo)
    show_ref(repo, refs, prefix="refs")

def cmd_tag(args):
    repo = get_repo_for_path()

    if args.name:
        # create a tag
        tag_create(repo, args.name, args.object, True if args.create_tag_object else False)
    else:
        # list all tags
        refs = ref_list(repo)
        show_ref(repo, refs["tags"], with_hash=False)

def cmd_rev_parse(args):
    if args.type:
        object_type = args.type.encode()
    else:
        object_type = None
    
    repo = get_repo_for_path()
    print(object_find(repo, args.name, object_type, follow=True))

def cmd_ls_files(args):
    repo = get_repo_for_path()
    index = index_read(repo)

    if args.verbose:
        print(f"Index file format v{index.version}, containing {index.entries} entries")
    
    for entry in index.entries:
        print(entry.name)
        if args.verbose:
            mode_dict = {0b1000: "regular file", 0b1010: "symlink", 0b1110: "git link"}
            
            print(f"  {mode_dict[entry.mode_type]} with perms: {entry.mode_perms:o}")
            print(f"  on blob: {entry.sha}")
            print(f"  created: {entry.ctime[0]}.{entry.ctime[1]}, modified: {entry.mtime[0]}.{entry.mtime[1]}")
            print(f"  device: {entry.dev}, inode: {entry.ino}")
            print(f"  user: {pwd.getpwuid(entry.uid).pw_name} ({entry.uid}), group: {grp.getgrgid(entry.gid).gr_name} ({entry.gid})")
            print(f"  flags: stage={entry.flag_stage} assume_valid={entry.flag_assume_valid}")

def cmd_check_ignore(args):
    repo = get_repo_for_path()
    rules = gitignore_read(repo)

    for path in args.path:
        if check_ignore(rules, path):
            print(path)

def cmd_status(args):
    repo = get_repo_for_path()
    index = index_read(repo)

    cmd_status_branch(repo)
    
    # changes to be committed --> how the staging area is different from the current HEAD
    cmd_status_head_index(repo, index)
    print()

    # changes not staged for commit:
    cmd_status_index_worktree(repo, index)

def cmd_rm(args):
    repo = get_repo_for_path()
    rm(repo, args.path)

def cmd_add(args):
    repo = get_repo_for_path()
    add(repo, args.path)

def add(repo, paths):
    # remove existing entries for these paths if they exist
    rm(repo, paths, delete=False, skip_missing=True)

    worktree = repo.worktree + os.sep

    # stores tuples of (absolute_path, path_relative_to_worktree)
    clean_paths = list()
    for path in paths:
        abspath = os.path.abspath(path)
        if not (abspath.startswith(worktree) and os.path.isfile(abspath)):
            raise Exception(f"Not a file, or outside the worktree: {paths}")
        relpath = os.path.relpath(abspath, repo.worktree)
        clean_paths.append((abspath, relpath))

    index = index_read(repo)

    for abspath, relpath in clean_paths:
        # store the object in the gitdir and get its hash
        with open(abspath, 'rb') as fp:
            sha = object_hash(fp, b'blob', repo)
        
        # get file system metadata and create a new index entry
        stat = os.stat(abspath)
        ctime_s = int(stat.st_ctime)
        ctime_ns = stat.st_ctime_ns % 10**9
        mtime_s = int(stat.st_mtime)
        mtime_ns = stat.st_mtime_ns % 10**9

        entry = IndexEntry(ctime=(ctime_s, ctime_ns), mtime=(mtime_s, mtime_ns), dev=stat.st_dev, ino=stat.st_ino,
                                mode_type=0b1000, mode_perms=0o644, uid=stat.st_uid, gid=stat.st_gid,
                                fsize=stat.st_size, sha=sha, flag_assume_valid=False,
                                flag_stage=False, name=relpath)
        index.entries.append(entry)
    
    index_write(repo, index)

def rm(repo, paths, delete=True, skip_missing=False):
    index = index_read(repo)

    worktree = repo.worktree + os.sep

    abspaths = set()
    for path in paths:
        abspath = os.path.abspath(path)
        if abspath.startswith(worktree):
            abspaths.add(abspath)
        else:
            raise Exception(f"Cannot remove paths outside of the worktree: {paths}")
    
    keep_entries = list()
    removed_paths = list()

    for entry in index.entries:
        full_path = os.path.join(repo.worktree, entry.name)
        if full_path in abspaths:
            removed_paths.append(full_path)
            abspaths.remove(full_path)
        else:
            keep_entries.append(entry)
    
    if len(abspaths) > 0 and not skip_missing:
        raise Exception(f"Cannot remove paths not in the index: {abspaths}")
    
    if delete:
        for path in removed_paths:
            os.unlink(path)
    
    index.entries = keep_entries
    index_write(repo, index)

def branch_get_active(repo):
    with open(get_path_to_repo_file(repo, "HEAD"), 'r') as fp:
        head = fp.read()
    
    if head.startswith("ref: "):
        return head[16:].strip('\n'), True # don't want the trailing \n
    
    return head.strip('\n'), False

def cmd_status_branch(repo):
    ref, is_branch = branch_get_active(repo)

    if is_branch:
        print(f"On branch {ref}.")
    else:
        print(f"HEAD deteached at {ref}")

def cmd_status_head_index(repo, index):
    print("Changes to be committed:")

    head_tree = tree_to_dict(repo, "HEAD")

    for entry in index.entries:
        if entry.name in head_tree:
            if head_tree[entry.name] != entry.sha:
                print(f"  modified: {entry.name}")
            del head_tree[entry.name]
        else:
            print(f"  added:  {entry.name}")
    
    # keys still in the head tree but not in index have been deleted
    for path in head_tree.keys():
        print(f"  deleted: {path}")

def cmd_status_index_worktree(repo, index):
    print("Changes not staged for commit:")

    ignore = gitignore_read(repo)

    gitdir_prefix = repo.gitdir + os.path.sep

    all_files = list()

    # walk the filesystem: remember repo.worktree is simply the root path for the repository
    for root, _, files in os.walk(repo.worktree, True):
        if root == repo.gitdir or root.startswith(gitdir_prefix):
            continue

        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, repo.worktree)
            # append path relative to repo root, since that's what we'll look for in the index file
            all_files.append(rel_path)
    
    for entry in index.entries:
        full_path = os.path.join(repo.worktree, entry.name)

        # if path is in index, but not in the file system, that that file is deleted.
        if not os.path.exists(full_path):
            print(f"  deleted  : {entry.name}")
        else:
            # creation and modification time acc to the file system
            stat = os.stat(full_path)

            # compare created and modification times

            ## creation and modification time acc to the index file
            ctime_ns = entry.ctime[0] * 10 ** 9 + entry.ctime[1]
            mtime_ns = entry.mtime[0] * 10 ** 9 + entry.mtime[1]

            if (stat.st_ctime_ns != ctime_ns) or (stat.st_mtime_ns != mtime_ns):
                # if times are different, deep compare
                # @FIXME This *will* crash on symlinks to dir.
                with open(full_path, "rb") as fp:
                    # get the hash for the blob object with current contents
                    sha = object_hash(fp, b'blob', None)

                    if entry.sha != sha:
                        print(f"  modified:  {entry.name}")
        
        # this is to get all the currently untracked files
        if entry.name in all_files:
            all_files.remove(entry.name)
    
    print("\nUntracked files:")

    for file in all_files:
        if not check_ignore(ignore, file):
            print(f" {file}")

def tag_create(repo, name, ref, create_object=False):
    sha = object_find(repo, ref)

    if create_object:
        tag = Tag()
        tag.init()
        tag.kvlm[b'object'] = sha.encode()
        tag.kvlm[b'type'] = b'commit' # TODO: this should be based on the actual object type
        tag.kvlm[b'tag'] = name.encode()
        tag.kvlm[b'tagger'] = b'gyatt <gyatt@gyatt.com>'
        tag.kvlm[None] = b'A tag generated by gyatt'
        tag_sha = object_write(tag, repo)

        ref_create(repo, "tags/" + name, tag_sha)
    else:
        ref_create(repo, "tags/" + name, sha)

def ref_create(repo, ref_name, sha):
    with open(get_path_to_repo_file(repo, "refs/", ref_name), 'w') as fp:
        fp.write(sha + '\n')

def show_ref(repo, refs, with_hash=True, prefix=""):
    for key, val in refs.items():
        if type(val) == str:
            print(f"{val + " " if with_hash else ""}{prefix + "/" if prefix else ""}{key}")
        else:
            show_ref(repo, val, with_hash=with_hash, prefix=f"{prefix}{"/" if prefix else ""}{key}")

def tree_checkout(repo, tree: Tree, path):
    for item in tree.items:
        obj = object_read(repo, item.sha)
        dest = os.path.join(path, item.path)

        if obj.object_type == b'tree':
            os.mkdir(dest)
            tree_checkout(repo, obj, dest)
        elif obj.object_type == b'blob':
            with open(dest, 'wb') as fp:
                fp.write(obj.serialize())

def ls_tree(repo, tree_ref, recursive=False, prefix=""):
    sha = object_find(repo, tree_ref, b'tree')
    obj = object_read(repo, sha)
    for item in obj.items:
        if len(item.mode) == 5:
            leaf_type = item.mode[:1]
        else:
            leaf_type = item.mode[:2]

        match leaf_type:
            case b'04': leaf_type = "tree"
            case b'10': leaf_type = "blob" # a regular file
            case b'12': leaf_type = "blob" # symlink. blob contents is link target
            case b'16': leaf_type = "commit" # submodule
            case _: raise Exception(f"Weird tree leaf node {item.mode}")
        
        if not (recursive and leaf_type=="tree"):
            print(f"{"0"*(6-len(item.mode)) + item.mode.decode('ascii')} {leaf_type} {item.sha}\t {os.path.join(prefix, item.path.decode('ascii'))}")
        else:
            ls_tree(repo, item.sha, recursive, os.path.join(prefix, item.path))

def log_graphviz(repo, sha, seen):
    if sha in seen:
        return
    
    seen.add(sha)

    commit = object_read(repo, sha)
    short_hash = sha[:8]
    message = commit.kvlm[None].decode('utf-8').strip()
    message = message.replace('\\', '\\\\')
    message = message.replace('"', '\\"')

    if "\n" in message: # get only first line
        message = message[:message.index('\n ')]
    
    print(f'  c_{sha} [label="{short_hash}: {message}"]')
    assert commit.object_type == b'commit'

    if not b'parent' in commit.kvlm.keys():
        return
    
    parents = commit.kvlm[b'parent']
    if type(parents) != list:
        parents = [parents]
    
    for p in parents:
        p = p.decode('ascii')
        print(f'  c_{sha} -> c_{p}')
        log_graphviz(repo, p, seen)


# entrypoint
def main(argv=sys.argv[1:]):
    args = argparser.parse_args(argv)
    match args.command:
        case "add"          : cmd_add(args)
        case "cat-file"     : cmd_cat_file(args)
        case "check-ignore" : cmd_check_ignore(args)
        case "checkout"     : cmd_checkout(args)
        case "commit"       : cmd_commit(args)
        case "hash-object"  : cmd_hash_object(args)
        case "init"         : cmd_init(args)
        case "log"          : cmd_log(args)
        case "ls-files"     : cmd_ls_files(args)
        case "ls-tree"      : cmd_ls_tree(args)
        case "rev-parse"    : cmd_rev_parse(args)
        case "rm"           : cmd_rm(args)
        case "show-ref"     : cmd_show_ref(args)
        case "status"       : cmd_status(args)
        case "tag"          : cmd_tag(args)
        case _              : print("Invalid command")

argparser = argparse.ArgumentParser(description="argument parser")

# enforce that `gyatt` must be called with a command --> `gyatt COMMAND`
argsubparsers = argparser.add_subparsers(title="Available commands", dest="command")
argsubparsers.required = True

init = argsubparsers.add_parser("init", help="Initialize a new, empty repository.")
init.add_argument("path", metavar="directory", nargs="?", default=".", help="Where to create the repository?")

cat_file_cmd = argsubparsers.add_parser("cat-file", help="Provide content of repository objects.")
cat_file_cmd.add_argument("type", metavar="type", choices=["blob", "tag", "commit", "tree"], help="Specify the type")
cat_file_cmd.add_argument("object", metavar="object", help="The object to display")

hash_object_cmd = argsubparsers.add_parser("hash-object", help="Compute object hash/ID and optionally create a blob from a file.")
hash_object_cmd.add_argument("-t", metavar="type", dest="type",
                              choices=["blob", "commit", "tag", "tree"],
                              default="blob",
                              help="Specify the type")
hash_object_cmd.add_argument("-w", dest="write", action="store_true", help="Actually write the object in the git repository")
hash_object_cmd.add_argument("path", help="Path to the object file")

log_cmd = argsubparsers.add_parser("log", help="Display the history of a given commit")
log_cmd.add_argument("commit", default="HEAD", nargs="?", help="Commit to start at")

ls_tree_cmd = argsubparsers.add_parser("ls-tree", help="Pretty print a tree object")
ls_tree_cmd.add_argument("-r", dest="recursive", action="store_true", help="Recurse into sub trees and get final objects.")
ls_tree_cmd.add_argument("tree", help="A treeish object")

# https://wyag.thb.lt/#cmd-checkout
checkout_cmd = argsubparsers.add_parser("checkout", help="Checkout a commit inside a directory.")
checkout_cmd.add_argument("commit", help="The commit or tree to checkout")
checkout_cmd.add_argument("path", help="The EMPTY directory to checkout on")

show_ref_cmd = argsubparsers.add_parser("show-ref", help="List references")

tag_cmd = argsubparsers.add_parser("tag", help="List or create tags")
tag_cmd.add_argument("-a", action="store_true", dest="create_tag_object", help="Whether to create a tag object")
tag_cmd.add_argument("name", nargs="?", help="Name of the tag")
tag_cmd.add_argument("object", default="HEAD", nargs="?", help="The object the new tag points to")

rev_parse_cmd = argsubparsers.add_parser("rev-parse", help="Parse revision (or other object) identifiers")
rev_parse_cmd.add_argument("--gyatt-type", metavar="type", dest="type", choices=['blob', 'commit', 'tag', 'tree'], default=None, help="Specify the expected type")
rev_parse_cmd.add_argument("name", help="The name to parse")

ls_files_cmd = argsubparsers.add_parser("ls-files", help="List all the staging area files")
ls_files_cmd.add_argument("--verbose", action="store_true", help="Show everything")

check_ignore_cmd = argsubparsers.add_parser("check-ignore", help="Check paths against ignore rules")
checkout_cmd.add_argument("path", nargs="+", help="Paths to check")

status_cmd = argsubparsers.add_parser("status", help="Show the working tree status")

rm_cmd = argsubparsers.add_parser("rm", help="Remove files from the working tree and the index")
rm_cmd.add_argument("path", nargs="+", help="Files to remove")

add_cmd = argsubparsers.add_parser("add", help="Add file contents to the index")
add_cmd.add_argument("path", nargs="+", help="Files to add to staging area")

# add(get_repo_for_path(), ['libgyatt.py'])
# rm(get_repo_for_path(), ['test.txt'])
# cmd_status({})
# cmd_ls_tree("02f5a2e1747525f47657c3efcc0753d9ffdc46a0")
# tag_create(get_repo_for_path(), "TEST", "311de2a48c30fd0fd92cf2f7ecf68ad1f8b35428", True)
# cat_file(get_repo_for_path(), 'master', 'tree')