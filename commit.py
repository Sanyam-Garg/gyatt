import collections
from object import Object

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
