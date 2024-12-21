import argparse, collections, os, re, sys
from datetime import datetime
import grp # read user groups database
import pwd # read users database
from fnmatch import fnmatch # to support patterns like "*.txt" in .gitignore
from math import ceil
from repository import *
from objects import *

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

# cmd_ls_tree("02f5a2e1747525f47657c3efcc0753d9ffdc46a0")