from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path
from traceback import print_exc

from jedi import Script, get_default_project
from jedi.api.classes import Name
from parso.tree import NodeOrLeaf, Leaf, BaseNode
from parso.python.tree import (
    PythonNode,
    Module,
    Keyword,
    Literal,
    Operator,
    EndMarker,
    ClassOrFunc,
    Name as TName,
)

from .writer import UimNodeWriter, UimTokenWriter, UimSearchIndexWriter
from .uim_pb2 import Location
from .timeout import setup_timeout, clear_timeout


_path_expansions = {}
_line_offsets = {}


def write_ws_and_comments(uim_node: UimTokenWriter, prefix: str, href: dict, real_line: int):
    # TODO
    uim_node.append_token('WS', prefix, href, real_line=real_line)


def expand_path(p: Path):
    if p not in _path_expansions:
        _path_expansions[p] = p.resolve()
    return _path_expansions[p]


def scan_line_offsets(code):
    offs = [0]
    o = 0
    for l in code.splitlines(keepends=True):
        o += len(l)
        offs.append(o)
    return offs


def get_offset(path: str, line, col):
    try:
        if path not in _line_offsets:
            with open(path) as f:
                _line_offsets[path] = scan_line_offsets(f.read())
        return _line_offsets[path][line-1] + col
    except Exception as e:
        raise KeyError(f'failed to resolve offset for {path}:{line}:{col}') from e


def loc_of(path: str, tree: NodeOrLeaf) -> Location:
    line, col = tree.start_pos
    return Location(
        line=line,
        column=col,
        offset=get_offset(path, line, col),
    )


def uni_href(path: str, tree: NodeOrLeaf) -> dict:
    line, col = tree.start_pos
    return {
        'path': path,
        'offset': get_offset(path, line, col),
    }


def tok_type(tree: Leaf) -> str:
    if isinstance(tree, Keyword):
        return 'Keyword'
    elif isinstance(tree, Literal):
        return 'Literal'
    elif isinstance(tree, Operator):
        return 'Punctuation'
    else:
        return 'Identifier'


class ScanQueue:
    def __init__(self, system: bool):
        self.system = system
        self.pending = set()
        self.processed = set()

    def add_dir(self, dir: Path):
        for f in dir.glob('**/*.py'):
            if 'site-packages' in f.parts:
                continue
            self.add_path(f)

    def add_imported(self, p: Path):
        if self.system:
            self.add_path(p)

    def add_path(self, p: Path):
        p = expand_path(p)
        if p not in self.processed:
            self.pending.add(p)

    def next(self):
        p = self.pending.pop()
        self.mark_processed(p)
        return p

    def mark_processed(self, p: Path):
        self.processed.add(p)

    def __bool__(self):
        return len(self.pending) > 0


@dataclass(frozen=True)
class G:
    path: str
    script: Script
    node_writer: UimNodeWriter
    search_writer: UimSearchIndexWriter
    uim_node: UimTokenWriter
    depth: int
    omit_initial_prefix: bool
    href: dict | None
    scan_queue: ScanQueue


def write_tree(g: G, tree: NodeOrLeaf):
    is_decorated = (isinstance(tree, PythonNode) and tree.type == 'decorated')
    if isinstance(tree, ClassOrFunc) or is_decorated:
        node = g.node_writer.begin_node(
            'Definition',
            g.path,
            start=loc_of(g.path, tree),
            nest_level=g.depth+1)
        if is_decorated:
            w = write_decorated
        else:
            w = write_content
        w(replace(g, uim_node=node, depth=g.depth+1, omit_initial_prefix=True), tree)
        g.node_writer.write_node(node)

        point_to = tree
        while (isinstance(point_to, PythonNode) and point_to.type == 'decorated'):
            point_to = point_to.children[-1]
        if getattr(point_to, 'name', None):
            point_to = point_to.name
        if is_decorated:
            we = write_elided_decorated_def
        else:
            we = write_elided_def
        we(replace(g, href=uni_href(g.path, point_to)), tree)

        if isinstance(point_to, TName):
            line, col = tree.start_pos
            g.search_writer.append(
                'IISymbol',
                point_to.value,
                {'path': g.path, 'offset': get_offset(g.path, line, col)},
                g.path,
                None)
    else:
        write_content(g, tree)


def write_decorated(g: G, tree: NodeOrLeaf):
    for c in tree.children:
        write_content(g, c)
        if g.omit_initial_prefix:
            g = replace(g, omit_initial_prefix=False)


def write_content(g: G, tree: NodeOrLeaf):
    if isinstance(tree, EndMarker):
        return

    if pf := getattr(tree, 'prefix', None):
        if not g.omit_initial_prefix:
            pline, _ = tree.get_start_pos_of_prefix()
            write_ws_and_comments(g.uim_node, pf, g.href, pline)
        g = replace(g, omit_initial_prefix=False)
    if isinstance(tree, Leaf):
        href = g.href
        if not href:
            locs = None
            if tree.value not in ['(', ')', ',', '=', '.', ':', '}', '\n']:
                try:
                    locs = g.script.goto(
                        tree.line,
                        tree.column,
                        follow_imports=True,
                        follow_builtin_imports=True)
                except TimeoutError:
                    raise
                except:
                    print_exc()
            if locs:
                name: Name = locs[0]
                if name.line is None or name.column is None or name.module_path is None:
                    if name.module_name != 'builtins':
                        print('no location for', name)
                else:
                    p = expand_path(name.module_path)
                    g.scan_queue.add_imported(p)
                    href = {
                        'path': str(p),
                        'offset': get_offset(p, name.line, name.column)
                    }
        g.uim_node.append_token(tok_type(tree), tree.value, href, real_line=tree.line)
    elif isinstance(tree, BaseNode):
        for c in tree.children:
            write_tree(g, c)
            if g.omit_initial_prefix:
                g = replace(g, omit_initial_prefix=False)
    else:
        raise ValueError(f'expected either a Leaf or a BaseNode, got {tree}')


def write_elided_def(g: G, df: ClassOrFunc):
    for c in df.children:
        write_content(g, c)
        if isinstance(c, Operator) and c.value == ':':
            g.uim_node.append_token('WS', ' …', g.href)
            break


def write_elided_decorated_def(g: G, df: PythonNode):
    for c in df.children:
        if isinstance(c, ClassOrFunc):
            write_elided_def(g, c)
            break
        write_content(g, c)


def scan_repo(repo_root, nodes_uim_path, search_uim_path, system=False):
    if not repo_root.exists():
        raise IOError(f'directory does not exist: {repo_root}')
    project = get_default_project(repo_root)

    scan_queue = ScanQueue(system=system)
    scan_queue.add_dir(repo_root)

    with (
        closing(UimNodeWriter(nodes_uim_path)) as uim_node_writer,
        closing(UimSearchIndexWriter(search_uim_path)) as search_writer,
    ):
        while scan_queue:
            path = scan_queue.next()
            print(f'[{len(scan_queue.processed)}/{len(scan_queue.pending) + len(scan_queue.processed)}] {path}')
            script = Script(path=path, project=project)
            path = str(path)

            module_node = script._module_node
            assert isinstance(module_node, Module)

            code = script._code
            assert isinstance(code, str)
            _line_offsets[path] = scan_line_offsets(code)

            file_node = uim_node_writer.begin_node('SourceFile', path, nest_level=0)

            g = G(
                path=path,
                script=script,
                node_writer=uim_node_writer,
                search_writer=search_writer,
                uim_node=file_node,
                depth=0,
                omit_initial_prefix=False,
                href=None,
                scan_queue=scan_queue)

            setup_timeout(120)
            try:
                for df in module_node.children:
                    write_tree(g, df)
            except TimeoutError:
                print_exc()
            finally:
                clear_timeout()

            uim_node_writer.write_node(file_node)
