import argparse
import logging
from pathlib import Path

from schemavcs.cli.commands import (
    branch_cmd,
    checkout_cmd,
    emit_ddl_cmd,
    generate_migration_cmd,
    init_cmd,
    merge_cmd,
    migrate_cmd,
)
from schemavcs.storage.paths import read_current_branch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="schemavcs")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init")

    branch = sub.add_parser("branch")
    branch_sub = branch.add_subparsers(dest="branch_command", required=True)
    branch_create = branch_sub.add_parser("create")
    branch_create.add_argument("name")
    branch_create.add_argument(
        "--from",
        dest="from_branch",
        required=False,
        default=None,
        help="defaults to the current branch",
    )

    checkout = sub.add_parser("checkout")
    checkout.add_argument("branch")

    migrate = sub.add_parser("migrate")
    migrate.add_argument(
        "--branch", required=False, default=None, help="defaults to the current branch"
    )
    migrate_sub = migrate.add_subparsers(dest="verb", required=True)

    create_table = migrate_sub.add_parser("create-table")
    create_table.add_argument("table")

    drop_table = migrate_sub.add_parser("drop-table")
    drop_table.add_argument("table")

    add_column = migrate_sub.add_parser("add-column")
    add_column.add_argument("table")
    add_column.add_argument("column")
    add_column.add_argument("type")
    add_column.add_argument("--nullable", action="store_true", default=True)
    add_column.add_argument("--not-null", dest="nullable", action="store_false")

    drop_column = migrate_sub.add_parser("drop-column")
    drop_column.add_argument("table")
    drop_column.add_argument("column")

    rename_column = migrate_sub.add_parser("rename-column")
    rename_column.add_argument("table")
    rename_column.add_argument("old_name")
    rename_column.add_argument("new_name")

    alter_type = migrate_sub.add_parser("alter-column-type")
    alter_type.add_argument("table")
    alter_type.add_argument("column")
    alter_type.add_argument("new_type")

    alter_nullability = migrate_sub.add_parser("alter-column-nullability")
    alter_nullability.add_argument("table")
    alter_nullability.add_argument("column")
    alter_nullability.add_argument("nullable", choices=["true", "false"])

    add_index = migrate_sub.add_parser("add-index")
    add_index.add_argument("table")
    add_index.add_argument("index_name")
    add_index.add_argument("--columns", required=True, help="comma-separated column names")
    add_index.add_argument("--unique", action="store_true")

    drop_index = migrate_sub.add_parser("drop-index")
    drop_index.add_argument("table")
    drop_index.add_argument("index_name")

    rename_index = migrate_sub.add_parser("rename-index")
    rename_index.add_argument("table")
    rename_index.add_argument("old_name")
    rename_index.add_argument("new_name")

    add_fk = migrate_sub.add_parser("add-foreign-key")
    add_fk.add_argument("table")
    add_fk.add_argument("--columns", required=True, help="comma-separated column names")
    add_fk.add_argument("--references", required=True, help="referenced table name")

    drop_constraint = migrate_sub.add_parser("drop-constraint")
    drop_constraint.add_argument("constraint_id")

    merge = sub.add_parser("merge")
    merge.add_argument("source", help="branch to merge in")
    merge.add_argument(
        "--into", dest="target", required=False, default=None, help="defaults to the current branch"
    )

    emit_ddl = sub.add_parser("emit-ddl")
    emit_ddl.add_argument(
        "--branch", required=False, default=None, help="defaults to the current branch"
    )

    sync = sub.add_parser("sync")
    sync.add_argument(
        "--branch", required=False, default=None, help="defaults to the current branch"
    )

    return parser


def dispatch(args: argparse.Namespace) -> None:
    repo_root: Path = args.repo

    if args.command == "init":
        init_cmd.run(repo_root)
        return

    if args.command == "branch":
        if args.branch_command == "create":
            branch_cmd.create(repo_root, args.name, args.from_branch)
        return

    if args.command == "checkout":
        checkout_cmd.run(repo_root, args.branch)
        return

    if args.command == "migrate":
        branch = args.branch or read_current_branch(repo_root)
        match args.verb:
            case "create-table":
                migrate_cmd.create_table(repo_root, branch, args.table)
            case "drop-table":
                migrate_cmd.drop_table(repo_root, branch, args.table)
            case "add-column":
                migrate_cmd.add_column(
                    repo_root, branch, args.table, args.column, args.type, args.nullable
                )
            case "drop-column":
                migrate_cmd.drop_column(repo_root, branch, args.table, args.column)
            case "rename-column":
                migrate_cmd.rename_column(
                    repo_root, branch, args.table, args.old_name, args.new_name
                )
            case "alter-column-type":
                migrate_cmd.alter_column_type(
                    repo_root, branch, args.table, args.column, args.new_type
                )
            case "alter-column-nullability":
                migrate_cmd.alter_column_nullability(
                    repo_root, branch, args.table, args.column, args.nullable == "true"
                )
            case "add-index":
                columns = [c.strip() for c in args.columns.split(",")]
                migrate_cmd.add_index(
                    repo_root, branch, args.table, args.index_name, columns, args.unique
                )
            case "drop-index":
                migrate_cmd.drop_index(repo_root, branch, args.table, args.index_name)
            case "rename-index":
                migrate_cmd.rename_index(
                    repo_root, branch, args.table, args.old_name, args.new_name
                )
            case "add-foreign-key":
                columns = [c.strip() for c in args.columns.split(",")]
                migrate_cmd.add_foreign_key(repo_root, branch, args.table, columns, args.references)
            case "drop-constraint":
                migrate_cmd.drop_constraint(repo_root, branch, args.constraint_id)
        return

    if args.command == "merge":
        target = args.target or read_current_branch(repo_root)
        merge_cmd.run(repo_root, target, args.source)
        return

    if args.command == "emit-ddl":
        branch = args.branch or read_current_branch(repo_root)
        emit_ddl_cmd.run(repo_root, branch)
        return

    if args.command == "sync":
        branch = args.branch or read_current_branch(repo_root)
        generate_migration_cmd.run(repo_root, branch)
        return


def main() -> None:
    parser = build_parser()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parser.parse_args()
    dispatch(args)


if __name__ == "__main__":
    main()
