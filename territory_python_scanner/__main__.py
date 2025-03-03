from argparse import ArgumentParser
from pathlib import Path

from .scanner import scan_repo

arg_parser = ArgumentParser()
arg_parser.add_argument('repo_root', type=Path)
arg_parser.add_argument('uim_dir', type=Path)
arg_parser.add_argument('--system', action='store_true')
args = arg_parser.parse_args()

repo_root: Path = args.repo_root
args.uim_dir.mkdir(exist_ok=True, parents=True)
nodes_uim_path = str(args.uim_dir / 'nodes.uim')
search_uim_path = str(args.uim_dir / 'search.uim')

scan_repo(repo_root, nodes_uim_path, search_uim_path, system=args.system)
