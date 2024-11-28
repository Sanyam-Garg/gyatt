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
import zlib, hashlib

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

def object_find(repo, name, type=None, follow=True):
    """
    Name resolution function based on the object identifier passed.
    """
    return name

class Blob(Object):
    """
    Blobs are user data. The content of every file you put in git is stored as a blob.
    """

    object_type=b'blob'

    def serialize(self):
        return self.blobdata
    
    def deserialize(self, data):
        self.blobdata = data