"""
At its core, git is a content-addressed file system. In regular file systems, the name of a file is arbitrary
and unrelated to its contents.
In git, the names of the files are dervied mathematically (SHA-1 hash) from their contents.
This has an important implication: "You don't modify a file in git; you create a new file in a different
                                    location."

A git object is simply this type of file in the repository.
Almost everything in git is stored as an object: source code, commits, tags (with some exceptions)

The first 2 characters of the SHA-1 hash of a file are used as the directory name, and the rest as a file name

Object storage format:
* Starts with its type: blob, commit, tag or tree, followed by an ASCII space (0x20), then the size of the
object in bytes as an ASCII number, then null (0x00), then the contents of the object.

The objects are compressed with zlib before storing.
"""

from repository import *
import zlib, hashlib, re

class Object():

    def __init__(self, data=None):
        if data:
            self.deserialize(data)
        else:
            self.init()
    
    def serialize(self, repo):
        """
        MUST be implemented by subclasses.
        Read object byte string from self.data and convert it into meaningful data.
        """
        raise Exception("Not implemented!")
    
    def deserialize(self, data):
        raise Exception("Not implemented!!")
    
    def init(self):
        pass

def object_read(repo, sha):
    """
    Read object from a git repository given its sha hash
    """
    path_to_object = get_path_to_repo_file(repo, "objects", sha[:2], sha[2:])

    if not os.path.isfile(path_to_object):
        return None
    
    with open(path_to_object, "rb") as fp:
        raw_object = zlib.decompress(fp.read())

        # Read object type
        space_index = raw_object.find(b' ')
        object_type = raw_object[:space_index]

        # Read and validate object size
        null_index = raw_object.find(b'\x00', space_index)
        object_size = int(raw_object[space_index+1:null_index].decode('ascii'))
        if object_size != len(raw_object) - null_index - 1:
            raise Exception(f"Malformed object {sha}: bad length")
        
        # Choose constructor
        match object_type:
            case b'commit': c = Commit
            case b'tree': c = Tree
            case b'tag': c = Tag
            case b'blob': c = Blob
            case _:
                raise Exception(f"Unknown type {object_type.decode('ascii')} for object {sha}")
        
        # Call constructor to build object
        return c(raw_object[null_index+1:])

def object_write(obj, repo=None):
    # Serialize object data
    obj_data = obj.serialize()

    # Add header
    result = obj.object_type + b' ' + str(len(obj_data)).encode() + b'\x00' + obj_data

    # Compute sha
    sha = hashlib.sha1(result).hexdigest()

    if repo:
        path = get_path_to_repo_file(repo, "objects", sha[:2], sha[2:], mkdir=True)

        if not os.path.exists(path):
            with open(path, 'wb') as fp:
                fp.write(zlib.compress(result))
    
    return sha

def object_resolve(repo, name):
    """
    Name resolution function based on the object identifier passed.

    This can be used to resolve:
    * the HEAD literal
    * short and long hashes
    * tags
    * branches
    * remote branches
    """
    candidates = list()
    hashRE = re.compile(f"^[0-9A-Fa-f]{4,40}$") # git has a minimum limit of 4 to be considered a short hash

    # empty string
    if not name.strip():
        return None
    
    if name == "HEAD":
        return [ref_resolve(repo, "HEAD")]
    
    # if hex string, try for a hash 
    if hashRE.match(name):
        name = name.lower()
        prefix = name[:2]
        path = get_path_to_repo_dir(repo, "objects", prefix)
        if path:
            remaining_hash = name[2:]
            for file in os.listdir(path):
                if file.startswith(remaining_hash):
                    candidates.append(prefix + file)
    
    # try for tag references
    as_tag = ref_resolve(repo, "refs/tags/" + name)
    if as_tag:
        candidates.append(as_tag)
    
    # try for local branches
    as_local_branch = ref_resolve(repo, "refs/heads/" + name)
    if as_local_branch:
        candidates.append(as_local_branch)
    
    # try for remote branches: "origin/master"
    as_remote_branch = ref_resolve(repo, "refs/remotes/" + name)
    if as_remote_branch:
        candidates.append(as_remote_branch)
    
    return candidates

def object_find(repo, name, type=None, follow=True):
    sha = object_resolve(repo, name)

    if not sha:
        raise Exception(f"No such reference {name}.")
    
    if len(sha) > 1:
        raise Exception(f"Ambiguous reference {name}: Candidates are \n - {"\n -".join(sha)}")
    
    sha = sha[0].strip('\n')

    if not type:
        return sha
    
    while True:
        # TODO: we are reading the entire object just to get the type. can be optimized.
        obj = object_read(repo, sha)

        if obj.object_type == type:
            return sha
        
        if not follow:
            return None
        
        # follow tags
        if obj.object_type == b'tag':
            sha = obj.kvlm[b'object'].decode('ascii')
        elif obj.object_type == b'commit' and type == b'tree':
            sha = obj.kvlm[b'tree'].decode('ascii')
        else:
            return None

def object_hash(fp, type, repo):
    """
    Hash object, write it to repo if not None.
    """
    data = fp.read()

    match type:
        case b'commit': obj=Commit(data)
        case b'tag': obj=Tag(data)
        case b'tree': obj=Tree(data)
        case b'blob': obj=Blob(data)
    
    return object_write(obj, repo)

class Blob(Object):
    """
    Blobs are user data. The content of every file you put in git is stored as a blob.
    """

    object_type=b'blob'

    def serialize(self):
        return self.blobdata
    
    def deserialize(self, data):
        self.blobdata = data

import collections

# key -> value list message
def kvlm_parse(raw_data, start=0, dct=None):
    if not dct:
        dct = collections.OrderedDict()
    
    next_spc = raw_data.find(b' ', start)
    next_nwline = raw_data.find(b'\n', start)

    if next_spc < 0 or (next_spc > next_nwline):
        # This means that we have already parsed all the key value pairs, and we are now onto
        # the message
        assert next_nwline == start
        dct[None] = raw_data[start+1:]
        return dct
    
    # else, we are still parsing key value pairs.
    key = raw_data[start:next_spc]

    # now the value for this key can be multiline. Remembering that each new line of a multiline 
    # value starts with a space, we try to find the last line of this value. Loop until we find a 
    # '\n' not followed by a space.
    end = start
    while True:
        end = raw_data.find(b'\n', end+1)
        if raw_data[end+1] != ord(' '):
            break
    
    value = raw_data[next_spc+1:end].replace(b'\n ', b'\n')

    # don't override existing key contents
    if key in dct:
        if type(dct[key]) == list:
            dct[key].append(value)
        else:
            dct[key] = [dct[key], value]
    else:
        dct[key] = value
    
    return kvlm_parse(raw_data, start=end+1, dct=dct)

def kvlm_serialize(kvlm):
    output = b''

    for key in kvlm.keys():
        if key == None: continue

        # normalize value to list
        val = kvlm[key]
        if type(val) != list:
            val = [val]
        
        for v in val:
            output += key + b' ' + (v.replace(b'\n', b'\n ')) + b'\n'
    
    # append message
    output += b'\n' + kvlm[None] + b'\n'
    return output

class Commit(Object):
    """
    Here's how a sample commit looks like: https://wyag.thb.lt/#orgf087d48
    * Subsequent lines of a multiline value start with a space that the parser must drop. Eg:
        PGP signature
    * tree: Ref to a tree object. It maps blobs IDs to file system locations. It is the actual
        content of the commit: file contents, and where they are stored.
    """
    object_type=b'commit'

    def deserialize(self, data):
        self.kvlm = kvlm_parse(data)

    def serialize(self):
        return kvlm_serialize(self.kvlm)
    
    def init(self):
        self.kvlm = collections.OrderedDict()

# Wrapper for a single record in the tree
class TreeLeaf(object):
    def __init__(self, mode, path, sha):
        self.mode = mode
        self.path= path
        self.sha = sha

def tree_parse_one_record(raw, start=0):
    space = raw.find(b' ', start)
    assert space - start == 5 or space - start == 6

    mode = raw[start:space]
    if len(mode) == 5:
        # normalize the mode to 6 bytes
        mode = b' ' + mode
    
    null_terminator = raw.find(b'\x00', space)
    path = raw[space+1:null_terminator]

    raw_sha = int.from_bytes(raw[null_terminator+1:null_terminator+21], "big")

    # convert to hex string, padded to 40 chars with zeroes if needed.
    sha = format(raw_sha, "040x")
    return null_terminator+21, TreeLeaf(mode, path, sha)

def tree_parse(raw):
    curr = 0
    max = len(raw)
    all_tuples = list()

    while curr < max:
        curr, data = tree_parse_one_record(raw, curr)
        all_tuples.append(data)
    
    return all_tuples

def tree_leaf_sort_key(leaf: TreeLeaf):
    """
    Directories are sorted with a final '/' at their end.
    """
    if leaf.mode.startswith(b'10'):
        return leaf.path
    else:
        return leaf.path + '/'

class Tree(Object):
    """
    https://wyag.thb.lt/#org5f03666
    Tree describes the contents of the work tree, maps the blobs --> path.
    Array of 3 element tuples (file_mode, path, sha-1)
    The SHA refers to either a blob or another tree.
    Format: [mode] space [path] 0x00 [sha-1]
    """
    object_type = b'tree'
    def serialize(self):
        return tree_serialize(self)
    
    def deserialize(self, data):
        self.items = tree_parse(data)
    
    def init(self):
        self.items = list()
    
def tree_serialize(tree: Tree):
    tree.items.sort(key=tree_leaf_sort_key)
    serialized_tree = b''

    for leaf in tree.items:
        serialized_tree += leaf.mode
        serialized_tree += b' '
        serialized_tree += leaf.path
        serialized_tree += b'\x00'
        sha = int(leaf.sha, 16)
        serialized_tree += sha.to_bytes(20, byteorder='big')

    return serialized_tree

class Tag(Commit):
    object_type = b'tag'

def ref_resolve(repo, ref):
    path = get_path_to_repo_file(repo, ref)

    if not os.path.exists(path):
        return None
    
    with open(path, 'r') as fp:
        content = fp.read()
    
    if content.startswith("ref: "):
        return ref_resolve(repo, content[5:].strip('\n'))
    return content

def ref_list(repo, path=None):
    if not path:
        path = get_path_to_repo_dir(repo, "refs")
    
    refs = collections.OrderedDict()

    for file in sorted(os.listdir(path)):
        file_path = os.path.join(path, file)

        if os.path.isdir(file_path):
            refs[file] = ref_list(repo, file_path)
        else:
            refs[file] = ref_resolve(repo, file_path)
    
    return refs