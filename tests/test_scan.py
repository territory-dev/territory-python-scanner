from pathlib import Path

from territory_python_scanner.scanner import scan_repo
from territory_python_scanner.uim_pb2 import Node


def test_scan(tmp_path):
    code = r'''from math import pi

text = f'The value of Pi is approx. {pi}'

def foo(a: str = None):
    return text

# multi line
# comment

def main():
    print(foo())  # comment


class A:
    a = 123

    def bar(self):
        return foo()


def decorate(f):
    return f


@decorate
def baz():
    pass


if __name__ == '__main__':
    def cond():
        pass

    main()
'''

    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'example.py').write_text(code)
    scan_repo(repo, tmp_path / 'nodes.uim', tmp_path / 'search.uim')

    output = read_length_prefixed_pbs(tmp_path / 'nodes.uim')
    exp = [dump_tagged(n) for n in output]
    assert exp == [
r'''5:0 (64) d1
def foo(a: str = None):
    return text
''',
r'''11:0 (129) d1
def main():
    print(foo())  # comment
''',
r'''18:4 (197) d2
def bar(self):
        return foo()
''',
r'''15:0 (171) d1
class A:
    a = 123

    def bar(self): …''',
r'''22:0 (235) d1
def decorate(f):
    return f
''',
r'''26:0 (267) d1
@decorate
def baz():
    pass
''',
r'''32:4 (330) d1
def cond():
        pass
''',
r'''0:0 (0) d0
from math import pi

text = f'The value of Pi is approx. {pi}'

def foo(a: str = None): …
# multi line
# comment

def main(): …

class A: …

def decorate(f): …

@decorate
def baz(): …

if __name__ == '__main__':
    def cond(): …
    main()
''',
    ]


def test_multiple_decorators(tmp_path):
    code = r'''
def decorate(f):
    return f


@decorate
@decorate
def f():
    pass

'''

    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'example.py').write_text(code)
    scan_repo(repo, tmp_path / 'nodes.uim', tmp_path / 'search.uim')

    output = read_length_prefixed_pbs(tmp_path / 'nodes.uim')
    exp = [dump_tagged(n) for n in output]
    assert exp == [
r'''2:0 (1) d1
def decorate(f):
    return f
''',
r'''6:0 (33) d1
@decorate
@decorate
def f():
    pass
''',
r'''0:0 (0) d0

def decorate(f): …

@decorate
@decorate
def f(): …''',
    ]



def read_varint(file):
    value = 0
    shift = 0

    while True:
        byte = file.read(1)
        if not byte:
            raise EOFError("Unexpected end of file while reading varint")

        b = ord(byte)
        value |= ((b & 0x7f) << shift)
        if not (b & 0x80):
            break
        shift += 7
        if shift > 64:
            raise ValueError("Varint too long (corrupt data)")

    return value


def read_length_prefixed_pbs(path):
    out = []
    with path.open('rb') as f:
        while True:
            try:
                l = read_varint(f)
            except EOFError:
                return out
            pb_bytes = f.read(l)
            n = Node()
            n.ParseFromString(pb_bytes)
            out.append(n)


def dump_tagged(n):
    o = []
    o.append(f'{n.start.line}:{n.start.column} ({n.start.offset}) d{n.uim_nest_level}\n')
    o.append(n.text)
    return ''.join(o)
