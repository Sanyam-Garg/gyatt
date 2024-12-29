from objects import get_path_to_repo_file
import os
from math import ceil

class IndexEntry():
    """
    Each index entry corresponds to a file. It is similar to an entry in the 'tree' object type,
    in addition to file system metadata.
    """
    def __init__(self, ctime=None, mtime=None, dev=None, ino=None,
                 mode_type=None, mode_perms=None, uid=None, gid=None,
                 fsize=None, sha=None, flag_assume_valid=None,
                 flag_stage=None, name=None):
        
        # the last time a file's metadata changed. tuple of (timestamp in seconds, nanoseconds)
        self.ctime = ctime

        # the last time a file's data changed. tuple of (timestamp in seconds, nanoseconds)
        self.mtime = mtime

        # the ID of the device containing this file
        self.dev = dev

        # file's inode number
        self.ino = ino

        # object type: b1000(regular), b1010(symlink), b1110(gitlink)
        self.mode_type = mode_type

        # object permissions, integer
        self.mode_perms = mode_perms

        # user ID of the owner
        self.uid = uid

        # group ID of the owner
        self.gid = gid

        # size of the object in bytes
        self.fsize = fsize

        self.sha = sha

        self.flag_assume_valid = flag_assume_valid

        self.flag_stage = flag_stage

        # full path to the object
        self.name = name

class Index():
    """
    Index file is a binary file. See index file format here:
    https://github.com/git/git/blob/master/Documentation/gitformat-index.txt
    This format was probably designed so index files could just be mmapp()ed to memory,
    and read directly as C structs, with an index built in O(n) time in most cases. 
    This kind of approach tends to produce more elegant code in C than in Python
    """

    def __init__(self, version=2, entries = None):
        if not entries:
            self.entries = list()
        
        self.version = version
        self.entries = entries

def index_read(repo):
    index_file = get_path_to_repo_file(repo, "index")

    # new repositories have no index file
    if not os.path.exists(index_file):
        return Index()
    
    with open(index_file, "rb") as fp:
        raw = fp.read()
    
    # extract the initial 12 bytes header
    header = raw[:12]
    signature = header[:4]
    assert signature == b'DIRC'
    version = int.from_bytes(header[4:8], "big")
    assert version == 2, "gyatt only supports index file version 2"
    count = int.from_bytes(header[8:12], "big")

    entries = list()

    content = raw[12:]
    idx = 0

    for i in range(count):
        # read creation time as unix timestamp: seconds since the "epoch"
        ctime_s = int.from_bytes(content[idx:idx+4], "big")
        
        # read creation time as nanoseconds after that timestamp, for extra precision
        ctime_ns = int.from_bytes(content[idx+4:idx+8], "big")

        # same for modification time
        mtime_s = int.from_bytes(content[idx+8:idx+12], "big")
        mtime_ns = int.from_bytes(content[idx+12:idx+16], "big")

        # device id
        dev = int.from_bytes(content[idx+16:idx+20], "big")

        # inode
        ino = int.from_bytes(content[idx+20:idx+24], "big")

        # ignored
        unused = int.from_bytes(content[idx+24:idx+26], "big")
        assert 0 == unused

        mode = int.from_bytes(content[idx+26:idx+28], "big")
        mode_type = mode >> 12
        assert mode_type in [0b1000, 0b1010, 0b1110]
        mode_perms = mode_type & 0b0000000111111111

        uid = int.from_bytes(content[idx+28:idx+32], "big")
        gid = int.from_bytes(content[idx+32:idx+36], "big")

        fsize = int.from_bytes(content[idx+36:idx+40], "big")

        # storing sha as lower case hex string for consistency
        sha = format(int.from_bytes(content[idx+40:idx+60]), "040x")

        # flags we are going to ignore
        flags = int.from_bytes(content[idx+60:idx+62], "big")

        # parse flags
        flag_assume_valid = (flags & 0b1000000000000000) != 0
        flag_extended = (flags & 0b0100000000000000) != 0
        assert not flag_extended
        flag_stage = flags & 0b0011000000000000

        # length of the name is stored in 12 bits --> max value is 4095.
        # since names can go beyond that length, git treats 0xfff as meaning "at least 4095",
        # and looks for the final 0x00 to find the end of the name.
        name_length = flags & 0b0000111111111111

        # we've read 62 bytes so far
        idx += 62

        if name_length < 0xfff:
            assert content[idx+name_length] == 0x00
            raw_name = content[idx:idx+name_length]
            idx += name_length + 1
        else:
            print(f"Notice: Name is 0x{name_length:X} bytes long.")
            null_idx = content.find(b'\x00', idx + 0xfff)
            raw_name = content[idx:null_idx]
            idx = null_idx + 1
        
        name = raw_name.decode('utf-8')

        # Data is padded on multiples of eight bytes for pointer
        # alignment, so we skip as many bytes as we need for the next
        # read to start at the right position.
        idx = 8 * ceil(idx / 8)

        entries.append(IndexEntry(ctime=(ctime_s, ctime_ns),
                                     mtime=(mtime_s,  mtime_ns),
                                     dev=dev,
                                     ino=ino,
                                     mode_type=mode_type,
                                     mode_perms=mode_perms,
                                     uid=uid,
                                     gid=gid,
                                     fsize=fsize,
                                     sha=sha,
                                     flag_assume_valid=flag_assume_valid,
                                     flag_stage=flag_stage,
                                     name=name))
    
    return Index(version=version, entries=entries)

def index_write(repo, index):
    with open(get_path_to_repo_file(repo, "index"), 'wb') as fp:

        # HEADER

        fp.write(b'DIRC')
        fp.write(index.version.to_bytes(4, 'big'))
        fp.write(len(index.entries).to_bytes(4, 'big'))

        # ENTRIES
        idx = 0
        for entry in index.entries:
            fp.write(entry.ctime[0].to_bytes(4, 'big'))
            fp.write(entry.ctime[1].to_bytes(4, 'big'))
            fp.write(entry.mtime[0].to_bytes(4, 'big'))
            fp.write(entry.mtime[1].to_bytes(4, 'big'))
            fp.write(entry.dev.to_bytes(4, 'big'))
            fp.write(entry.ino.to_bytes(4, 'big'))

            # mode
            mode = (entry.mode_type << 12) | entry.mode_perms
            # this covers unused part as well
            fp.write(mode.to_bytes(4, 'big'))

            fp.write(entry.uid.to_bytes(4, 'big'))
            fp.write(entry.gid.to_bytes(4, 'big'))

            fp.write(entry.fsize.to_bytes(4, 'big'))
            fp.write(int(entry.sha, 16).to_bytes(20, 'big'))

            flag_assume_valid = 0x1 << 15 if entry.flag_assume_valid else 0

            name_bytes = entry.name.encode('utf-8')
            name_bytes_len = len(name_bytes)
            if name_bytes_len > 0xfff:
                name_length = 0xfff
            else:
                name_length = name_bytes_len
            
            # merge back the 2 flags and the length of the name on the same 2 bytes
            fp.write((flag_assume_valid | entry.flag_stage | name_length).to_bytes(2, 'big'))

            fp.write(name_bytes)

            fp.write((0).to_bytes(1, 'big'))

            idx += 62 + len(name_bytes) + 1

            if idx % 8 != 0:
                # padding
                pad = 8 - (idx % 8)
                fp.write((0).to_bytes(pad, 'big'))
                idx += pad 