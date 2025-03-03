from pathlib import Path

from territory_python_scanner.scanner import scan_repo
from territory_python_scanner.uim_pb2 import Node


def test_scan(tmp_path):
    scan_repo(Path(__file__).parent / '../../../repos/py', tmp_path / 'nodes.uim', tmp_path / 'search.uim')

    output = read_length_prefixed_pbs(tmp_path / 'nodes.uim')
    exp = [dump_tagged(n) for n in output]
    assert exp == [
r'''5:0 (64)
def foo(a: str = None):
    return text
''',
r'''11:0 (129)
def main():
    print(foo())  # comment
''',
r'''18:4 (197)
def bar(self):
        return foo()
''',
r'''15:0 (171)
class A:
    a = 123

    def bar(self): …''',
r'''22:0 (235)
def decorate(f):
    return f
''',
r'''27:0 (277)
def baz():
    pass
''',
r'''26:0 (267)
@decorate
def baz(): …''',
r'''32:4 (330)
def cond():
        pass
''',
r'''0:0 (0)
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
            n .ParseFromString(pb_bytes)
            out.append(n)


def dump_tagged(n):
    o = []
    o.append(f'{n.start.line}:{n.start.column} ({n.start.offset})\n')
    o.append(n.text)
    return ''.join(o)
