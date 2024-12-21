from objects import *
import os
import collections

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