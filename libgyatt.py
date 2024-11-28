import argparse, collections, os, re, sys
from datetime import datetime
import grp # read user groups database
import pwd # read users database
from fnmatch import fnmatch # to support patterns like "*.txt" in .gitignore
from math import ceil
from repository import *
from object import *

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