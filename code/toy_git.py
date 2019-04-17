import collections, hashlib, os, struct, enum
import zlib, time, subprocess, requests, urllib

from user import *


class ObjectType(enum.Enum):
    """
    枚举类    
    """
    commit = 1
    tree = 2
    blob = 3


# git index (.git/index) 里面的一个入口
IndexEntry = collections.namedtuple('IndexEntry', [
    'ctime_s', 'ctime_n', 'mtime_s', 'mtime_n', 'dev', 'ino', 'mode', 'uid',
    'gid', 'size', 'sha1', 'flags', 'path',
])

def write_file(path, data):
    with open(path, 'wb') as f:
        f.write(data)

def read_file(path):
    with open(path, 'rb') as f:
        return f.read()


def read_index(path):
    entrys = []
    return entrys


def build_lines_data(lines):
    """
    给服务器发送数据的一些格式，复制粘贴
    """
    result = []
    for line in lines:
        result.append('{:04x}'.format(len(line) + 5).encode())
        result.append(line)
        result.append(b'\n')
    result.append(b'0000')
    return b''.join(result)


def extract_lines(data):
    """
    data 长这样
    b'001f# service=git-receive-pack\n0000009d47241f74a2b076321f1870d73ea694c85bcd7e30 refs/heads/master\x00report-status delete-refs side-band-64k quiet atomic ofs-delta agent=git/github-g4f6c801f9475\n0000'
    
    最后要变成
    [b'# service=git-receive-pack\n', b'', b'47241f74a2b076321f1870d73ea694c85bcd7e30 refs/heads/master\x00report-status delete-refs side-band-64k quiet atomic ofs-delta agent=git/github-g4f6c801f9475\n', b'']
    前面的数字代表后面数据的长度

    每四个读取
    """
    lines = []
    i = 0
    while True:
        length = int(data[i:i+4], 16)
        line = data[i+4: i+length]
        lines.append(line)
        if length == 0:
            i += 4
        else :
            i += length

        if i >= len(data):
            break

    return lines

def http_request(url, username, password, method='GET', data=None):
    r = None
    if method == 'GET':
        r = requests.get(url, auth=(username, password), data=data)
    else:
        r = requests.post(url, auth=(username, password), data=data)
    return r.content



class ToyGit():
    def __init__(self, root):
        self.root = root
        self.git = os.path.join(root, '.git')

    def write_file(self, path, data):
        path = os.path.join(self.root, path)
        return write_file(path, data)

    def read_file(self, path):
        path = os.path.join(self.root, path)
        return read_file(path)


    def encode_pack_object(self, obj):
        """
        打包文件，固定格式，复制粘贴
        """

        obj_type, data = self.read_object(obj)
        type_num = ObjectType[obj_type].value
        size = len(data)
        byte = (type_num << 4) | (size & 0x0f)
        size >>= 4
        header = []
        while size:
            header.append(byte | 0x80)
            byte = size & 0x7f
            size >>= 7
        header.append(byte)
        return bytes(header) + zlib.compress(data)

    def init(self, repo_path):
        """
        创建多个目录，以及 HEAD 文件
        1. .git
        2. .git 下 objects refs refs/heads 目录
        3. HEAD 文件 b'ref: refs/heads/master'
        """
        e = os.path.exists(os.path.join(repo_path, '.git'))
        if e:
            print('repository exists: {}'.format(repo_path))
            return
        os.mkdir(os.path.join(repo_path, '.git'))
        dirs = ['objects', 'refs', 'refs/heads']
        for d in dirs:
            os.mkdir(os.path.join(repo_path, '.git', d))
        self.write_file(os.path.join('.git', 'HEAD'), b'ref: refs/heads/master')
        print('initialized empty repository: {}'.format(repo_path))

    def read_index(self):
        """
        1. data[:-20].digest() 等于 data[-20:].digest()
        2. signature(4s)==b'DIRC' version(L)==2 num_entries(L) 存在前 data[:12]
        3. 每个 entry 的开头 有 62 个字节 这 62 个字节存着文件信息(LLLLLLLLLL20sH)
        4. 接下来是文件名，结尾是 b'\x00'
        5. 文件名后面是 n 个 b'\x00' 这 n 个用来凑 8 的倍数
        """
        try:
            data = self.read_file('.git/index')
        except FileNotFoundError:
            return []

        digest = hashlib.sha1(data[:-20]).digest()
        assert digest == data[-20:], 'error index'
        header = data[:12]
        signature, version, num_entries = struct.unpack('!4sLL', header)
        assert signature == b'DIRC', 'error signature'
        assert version == 2, 'error version'
        entry_data = data[12:-20]
        entrys = []
        i = 0

        while(i + 62 < len(entry_data)):
            header_end = i + 62
            entry_header = entry_data[i:header_end]
            # 获得 entry 头
            header = struct.unpack('!LLLLLLLLLL20sH', entry_header)
            # 获得文件名，找到 b'\x00'
            path_end = entry_data.index(b'\x00', header_end)
            path = entry_data[header_end:path_end]
            entry = IndexEntry(*(header + (path.decode(),)))
            entrys.append(entry)
            entry_len = (62 + len(path) + 8) // 8 * 8
            i += entry_len
        return entrys

    def hash_object(self, data, obj_type, write=True):
        """
        在 objects 里面写入文件
        有三种格式 
        1. blob 普通文件
        2. tree
        3. commit 
        """
        header = '{} {}'.format(obj_type, len(data)).encode()
        full_data = header + b'\x00' + data
        sha1 = hashlib.sha1(full_data).hexdigest()
        if write:
            path = os.path.join(self.root, '.git', 'objects', sha1[:2], sha1[2:])
            if not os.path.exists(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                write_file(path, zlib.compress(full_data))
        return sha1

    def write_index(self, entrys):
        """
        1. 头部前 12 个字符
        2. 尾部是由 前面的所有字符 hashlib.sha1() 得来的
        3. 中间是每一个 entry 连续放在一起。每个 entry 有 62 个字节的头，LLLLLLLLLL20sH
            然后是 path 最后是填充的 b'\x00' 长度要是 8 的倍数
            如果 entry + path 长度是 8 的倍数那么添加 8 个 b'\x00'
            这里有一个小技巧 可以看我的博客
            https://www.jianshu.com/p/570b61384720

        4. 把 add 过的文件都放入 index 中。也就是这次 add + 之前 add
        """
        signature, version, num_entries = b'DIRC', 2, len(entrys)
        header = struct.pack('!4sLL', signature, version, num_entries)
        packed_entrys = []
        for entry in entrys:
            entry_head = struct.pack('!LLLLLLLLLL20sH',
                entry.ctime_s, entry.ctime_n, entry.mtime_s, entry.mtime_n,
                entry.dev, entry.ino, entry.mode, entry.uid, entry.gid,
                entry.size, entry.sha1, entry.flags)
            path = entry.path.encode()
            length = ((62 + len(path) + 8) // 8) * 8
            packed_entry = entry_head + path + b'\x00' * (length - 62 - len(path))
            packed_entrys.append(packed_entry)
        all_data = header + b''.join(packed_entrys)
        digest = hashlib.sha1(all_data).digest()
        all_data += digest
        self.write_file('.git/index', all_data)
    
    def write_tree(self):
        """
        把当前的 index 写入树中
        写法与普通文件一样，
        tree_entry mode_path + b'\x00' + index 的 entry.sha1
        model_path = '{:o} {}'.format(entry.mode, entry.path)
        """
        tree_entrys = []
        for entry in self.read_index():
            assert '/' not in entry.path, \
                'currently only supports a single, top-level directory'
            model_path = '{:o} {}'.format(entry.mode, entry.path).encode()
            tree_entry = model_path + b'\x00' + entry.sha1
            tree_entrys.append(tree_entry)

        return self.hash_object(b''.join(tree_entrys), 'tree')


    def add(self, file_paths):
        """
        只支持文件 不支持目录和 .
        而且只支持根目录的文件
        不支持删除


        1. 标准化路径不能有 \\
        2. 读取所有的索引
        3. 生成新的索引
        4. 索引按 path 排序
        5. 写入新的索引
        """
        paths = [p.replace('\\', '/') for p in file_paths]
        all_entrys = self.read_index()
        entrys = [e for e in all_entrys if e.path not in paths]
        for path in paths:
            real_path = os.path.join(self.root, path)
            sha1 = self.hash_object(read_file(real_path), 'blob')
            st = os.stat(real_path)
            flags = len(path.encode())
            assert flags < (1 << 12)
            entry = IndexEntry(
                int(st.st_ctime), 0, int(st.st_mtime), 0, st.st_dev,
                st.st_ino, st.st_mode, st.st_uid, st.st_gid, st.st_size,
                bytes.fromhex(sha1), flags, path)
            entrys.append(entry)
        entrys.sort(key=lambda x: x.path)
        self.write_index(entrys)

    def get_local_master_hash(self):
        """
        得到 local commit 
        存在 .git/refs/heads/master 中
        """
        master_path = os.path.join('.git', 'refs', 'heads', 'master')
        try:
            return self.read_file(master_path).decode().strip()
        except FileNotFoundError:
            return None

    def commit(self, message, author=None, email=None):
        """
        提交：
        1. 把当前 index 写入树中
        2. 得到上一次提交的 commit 在 ./git/refs/heads/master 中
        3. 讲所有的数据放在一起 [当前 index， 上一次提交的 commit, author, committer, '', messge, '']
        4. 将这些内容通过 hash_object 写入 objects 文件夹中 commit
        """
        tree = self.write_tree()
        parent = self.get_local_master_hash()
        author = '{} <{}>'.format(author, email)

        timestamp = int(time.mktime(time.localtime()))
        utc_offset = -time.timezone
        # 提交时间，我实在不是很理解他是怎么得到的，所以就抄了
        author_time = '{} {}{:02}{:02}'.format(
                timestamp,
                '+' if utc_offset > 0 else '-',
                abs(utc_offset) // 3600,
                (abs(utc_offset) // 60) % 60)

        lines = ['tree ' + tree]
        if parent:
            lines.append('parent ' + parent)
        lines.append('author {} {}'.format(author, author_time))
        lines.append('committer {} {}'.format(author, author_time))
        lines.append('')
        lines.append(message)
        lines.append('')
        data = '\n'.join(lines).encode()
        sha1 = self.hash_object(data, 'commit')
        master_path = os.path.join('.git', 'refs', 'heads', 'master')
        self.write_file(master_path, (sha1 + '\n').encode())
        print('committed to master: {:7}'.format(sha1))
        return sha1

    def get_remote_master_hash(self, git_url, username, password):
        """
        给 git_url + '/info/refs?service=git-receive-pack' 发送 get 请求
        得到
        b'001f# service=git-receive-pack\n0000009df4ec14ac450c26a434bed650df3270eadbac3676 refs/heads/master\x00
        report-status delete-refs side-band-64k quiet atomic ofs-delta agent=git/github-g810e442cedb5\n0000'
        这样的二进制
        里面存着远程仓库的 commit
        """
        url = git_url + '/info/refs?service=git-receive-pack'
        res = http_request(url, username, password)

        lines = extract_lines(res)
        assert lines[0] == b'# service=git-receive-pack\n'
        assert lines[1] == b''
        if lines[2][:40] == b'0' * 40:
            return None

        master_sha1, master_ref = lines[2].split(b'\x00')[0].split()
        assert master_ref == b'refs/heads/master'
        assert len(master_sha1) == 40
        return master_sha1.decode()


    def read_tree(self, tree_sha1):
        """
        与 write_tree 相反
        """
        obj_type, data = self.read_object(tree_sha1)
        assert obj_type == 'tree'
        i = 0
        entrys = []
        while True:
            end = data.find(b'\x00', i)
            if end == -1:
                break
            mode_str, path = data[i:end].decode().split()
            mode = int(mode_str, 8)
            digest = data[end + 1:end + 21]
            entrys.append((mode, path, digest.hex()))
            i = end + 21
        return entrys
            


    def find_tree_objects(self, tree_sha1):
        """
        由于只提交单个文件，所以不去判断 mode。

        把 tree 里面的 sha1（objetcs 文件夹里面的文件路径） 
        """
        objects = {tree_sha1}
        for mode, path, sha1 in self.read_tree(tree_sha1):
            objects.add(sha1)
        return objects

    def read_object(self, object_sha1):
        obj_path = os.path.join('.git', 'objects', object_sha1[:2], object_sha1[2:])
        obj_data = self.read_file(obj_path)
        full_data = zlib.decompress(obj_data)
        nul_index = full_data.index(b'\x00')
        header = full_data[:nul_index]
        obj_type, size_str = header.decode().split()
        size = int(size_str)
        data = full_data[nul_index + 1:]
        assert size == len(data), 'expected size {}, got {} bytes'.format(
            size, len(data))
        return (obj_type, data)

    def find_commit_objects(self, commit_sha1):
        """
        1. 通过 sha1 找到 objects 里文件所在位置并读取
        2. 读取里面的 tree 的 sha1
        3. 把 tree 的 sha1 放进 set 里面
        """
        objects = {commit_sha1}
        obj_type, commit = self.read_object(commit_sha1)
        assert obj_type == 'commit'
        lines = commit.decode().split('\n')
        # 找到第一个 tree sha1
        tree = next(l[5:45] for l in lines if l.startswith('tree '))
        objects.update(self.find_tree_objects(tree))
        # 找到所有的 parent
        parents = (l[7:47] for l in lines if l.startswith('parent '))
        for parent in parents:
            objects.update(self.find_commit_objects(parent))

        return objects

    def find_missing_objects(self, local_sha1, remote_sha1):
        """
        local_objects 和 remote_objects 都是 set 类
        两者相减得到不一样的地方
        """
        local_objects = self.find_commit_objects(local_sha1)
        if remote_sha1 is None:
            return local_objects
        remote_objects = self.find_commit_objects(remote_sha1)
        return local_objects - remote_objects
        
    def creat_pack(self, objects):
        header = struct.pack('!4sLL', b'PACK', 2, len(objects))
        body = b''.join(self.encode_pack_object(o) for o in sorted(objects))
        contents = header + body
        sha1 = hashlib.sha1(contents).digest()
        data = contents + sha1
        return data

    def push(self, git_url, username=None, password=None):
        """
        1. 得到远程仓库的 commit 
        2. 拿到 push 之前的 commit
        3. 从 objects 文件里面的， 拿到两次 commit
        4. 通过 commit 里面的 tree 比较 commit 所提交的文件的不同
        5. 打包上传所差的文件 
        """
        assert username != None and password !=None, 'please enter username and password'
        remote_sha1 = self.get_remote_master_hash(git_url, username, password)
        local_sha1 = self.get_local_master_hash()
        missing = self.find_missing_objects(local_sha1, remote_sha1)
        print('updating remote master from {} to {} ({} object{})'.format(
            remote_sha1 or 'no commits', local_sha1, len(missing),
            '' if len(missing) == 1 else 's'))
        lines = ['{} {} refs/heads/master\x00 report-status'.format(
            remote_sha1 or ('0' * 40), local_sha1).encode()]
        data = build_lines_data(lines) + self.creat_pack(missing)
        url = git_url + '/git-receive-pack'
        response = http_request(url, username, password, 'POST', data)
        lines = extract_lines(response)
        
        



def main():
    repo_path = os.getcwd()
    tg = ToyGit(repo_path)
    tg.init(os.path.join(tg.root))
    tg.add(['toy_git.py'])
    tg.commit('toy_git.py', GIT_AUTHOR_NAME, GIT_AUTHOR_EMAIL)
    tg.push(GIT_URL, GIT_USERNAME, GIT_PASSWORD)


if __name__ == "__main__":
    main()
