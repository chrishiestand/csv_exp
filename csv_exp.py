#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    =======================
    CSV Exporter for Oracle
    =======================

    Copyright © 2017 Dbvisit Software Ltd, < http://dbvisit.com >

    This program uses cx_Oracle_ module to connect to the Oracle Database.
    Copyright © 2007-2015, Anthony Tuininga. All rights reserved.
    Copyright © 2001-2007, Computronix (Canada) Ltd., Edmonton, Alberta,
        Canada. All rights reserved.

    This program is NOT SUPPORTED by Dbvisit Software Ltd., and is not
    covered by Dbvisit Software Suppport Agreement. See README.rst and
    LICENSE for more details.

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, write to the Free Software
    Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.


    .. warning::

      LOBS and LONGs might never be the same again after exporting. Especially
      with binary data.

    .. _cx_Oracle: https://bitbucket.org/anthony_tuininga/cx_oracle
"""
import sys
import os
import csv
import argparse
import hashlib
import mimetypes

from timeit import default_timer as timer

import magic

try:
    import cx_Oracle
except ImportError:
    print("No cx_Oracle module available.\nTo install, run:\n"
          "\tpip install cx_Oracle", file=sys.stderr)
    sys.exit(1)

# default number of rows per write
DEFAULT_ARRAY = 16384
# output column names
OUTPUT_HEADER = True
# current version
VERSION = '0.2.1'
# unsupported types
UNSUPPORTED_TYPES = ['INTERVAL YEAR(2) TO MONTH']
# default NULL
NULL_AS = None
# default line terminator for CSV file
LINETERM = '\n'

binary_type_map = {cx_Oracle.BINARY: 'RAW', cx_Oracle.LONG_BINARY: 'LONG RAW', cx_Oracle.BLOB: 'BLOB'}

def get_safe_columns(conn, table, exclude=None):
    """Get the list of columns and filter out the unsupported ones

    :param cx_Oracle.connect conn: Oracle connection (must be established)
    :param str table: table name - can be SCHEMA.TABLE or just TABLE.
    :param list exclude: list of columns to exclude. These must have the
        same for of table_name as specified in `table` parameter, otherwise
        they will be ignored. For example, if table is specified as: ``TAB``,
        columns should be listed as ``['TAB.COL1','TAB.COL2']``. If table
        is defined as ``SCOTT.TAB``, the column list should include both
        table and schema: ``['SCOTT.TAB.COL1','SCOTT.TAB.COL2']``.

    :return: list of safe columns with unsupported types as '' and those
        which are marked for exclusion - excluded.
    """
    obj = table.split(".")
    to_exclude_str = None
    if exclude:
        # determine if there are some columns to exlude from this table
        to_exclude_str = ",".join(["'{0}'".format(col.split(".")[-1])
                                   for col in exclude
                                   if col.startswith(table)])

    if len(obj) == 0 or len(obj) > 2:
        raise ValueError("Failed to parse table name: {0}".format(table))
    elif len(obj) == 1:
        stmt = """
            SELECT COLUMN_NAME,DATA_TYPE
              FROM USER_TAB_COLUMNS
             WHERE TABLE_NAME = :1
               """
        binds = [obj[0], ]
    elif len(obj) == 2:
        stmt = """
            SELECT COLUMN_NAME,DATA_TYPE
              FROM ALL_TAB_COLUMNS
             WHERE TABLE_NAME = :1
               AND OWNER = :2
               """
        binds = [obj[1], obj[0], ]

    if to_exclude_str:
        stmt = stmt + " AND COLUMN_NAME NOT IN ({0}) ".format(to_exclude_str)
    stmt = stmt + ' ORDER BY COLUMN_ID'
    cur = conn.cursor()
    cur.execute(stmt, binds)
    columns = cur.fetchall()
    cur.close()

    safe_columns = list()
    for col in columns:
        if col[1] not in UNSUPPORTED_TYPES:
            safe_columns.append('"{0}"'.format(col[0]))
        else:
            sys.stderr.write("* WARNING: Skipping column: {0}. Unsupported "
                             "type: {1}\n".format(col[0], col[1]))
            safe_columns.append("'' AS \"{0}\"".format(col[0]))

    return safe_columns


def exp_schema(conn, schema, scn=None, exclude=None, output_path=None):
    """Export SCHEMA

    :param cx_Oracle.connect conn: Oracle connection (must be established)
    :param str schema: schema name

    """
    tabs = conn.cursor()
    tabs.execute("SELECT OWNER||'.'||TABLE_NAME FROM ALL_TABLES "
                 "WHERE OWNER = :1", (schema,))
    for row in tabs:
        exp_table(conn, row[0], scn, exclude, output_path)


def exp_table(conn, table, scn=None, exclude=None, output_path=None):
    """Export TABLE

    Export given <table> to the <table>.csv file

    :param cx_Oracle.connect conn: Oracle connection (must be established)
    :param str schema: table name.  Can be specified as "SCHEMA.TABLE" or just
        "TABLE".

    """
    sys.stderr.write("EXPORTING: {0}...\n".format(table))
    columns = ",".join(get_safe_columns(conn, table, exclude))
    stmt = 'SELECT {0} FROM {1}'.format(columns,
                                        table)
    if scn is not None:
        stmt = stmt + ' AS OF SCN {0}'.format(str(scn))

    filename        = "{0}.csv".format(table)
    csv_path        = os.path.join(output_path, filename)
    binary_path     = os.path.join(output_path, table)
    binary_rel_path = os.path.relpath(binary_path, output_path)

    with open(csv_path, "w") as f:
        exp_sql(conn, f, stmt, binary_path, binary_rel_path)


def exp_sql(conn, file_handle, stmt, binary_path=None, binary_rel_path=None):
    """Data exporter

    Runs statement and outputs the result to file_handle in csv format.

    :param cx_Oracle.connect conn: Oracle connection (must be established)
    :param id file_handle: file handle. File should be open for writing.
        Can be a `sys.stdout` as well.
    :param str stmt: statement to execute

    """

    start = timer()

    stmt=stmt.strip().rstrip(";")
    cur = conn.cursor()
    cur.execute(stmt)

    rowcount = 0

    rows = cur.fetchmany(DEFAULT_ARRAY)
    binary_by_filename = {}

    csv_writer = csv.writer(file_handle, dialect="unix",
                            lineterminator=LINETERM)
    if OUTPUT_HEADER:
        csv_writer.writerow([c[0] for c in cur.description])

    while len(rows) > 0:

        rowcount += len(rows)

        if binary_path and binary_rel_path:
            rows, binary_by_filename = transform_row_binary(cur.description, binary_rel_path, rows)

        if len(binary_by_filename):
            try:
                os.mkdir(binary_path, mode=0o700)
            except FileExistsError:
                pass

        for hash, binary in binary_by_filename.items():

            write_path = os.path.join(binary_path, hash)

            if os.path.exists(write_path):
                print("file {0} already exists, skipping".format(write_path), file=sys.stderr)
                continue

            with open(write_path, mode='bx') as f:
                f.write(binary)
                f.close()

        # Substitute null with the requred value
        if NULL_AS:
            for r in range(0, len(rows)):
                if None in rows[r]:
                    row = list(rows[r])
                    for i in range(0, len(row)):
                        if row[i] is None:
                            row[i] = NULL_AS
                    rows[r] = row

        csv_writer.writerows(rows)
        print('.', end='', file=sys.stderr)
        rows = cur.fetchmany(DEFAULT_ARRAY)

    cur.close()

    stop = timer()
    duration_s = round(stop - start, 3)
    rate = round(rowcount / duration_s, 2)

    print("exported {0} rows in {1}s {2}rows/s from sql '{3}'".format(rowcount, duration_s, rate, stmt), file=sys.stderr)


def transform_row_binary(cx_description, binary_rel_path, rows):

    binary_cols = binaryColumnIdxs(cx_description, rows)
    binary_by_filename = {}

    if not len(binary_cols):
        return rows, binary_by_filename

    for ri, row in enumerate(rows):
        for col in binary_cols:

            objOrBytes = row[col]

            # cx_Oracle.BLOB gives object, RAW returns bytes
            if hasattr(objOrBytes, 'read') and callable(objOrBytes.read):
                data = objOrBytes.read()
            else:
                data = objOrBytes

            if not data:
                print("binary data is empty, skipping column {0} in row: {0}".format(col, row), file=sys.stderr)
                l = list(row)
                l[col] = ''
                rows[ri] = tuple(l)
                continue

            extension = detectFileExtension(data)

            m = hashlib.sha256()
            m.update(data)
            hash = m.hexdigest()

            if extension:
                filename = "{0}{1}".format(hash, extension)
            else:
                filename = hash

            binary_by_filename[filename] = data
            l = list(row)
            l[col] = "file://{0}/{1}".format(binary_rel_path, filename)
            rows[ri] = tuple(l)

    return rows, binary_by_filename

# Returns empty string "" or ".ext"
def detectFileExtension(byts):
    mime_data = magic.from_buffer(byts, mime=True)

    if not mime_data:
        return ''

    extension = mimetypes.guess_extension(mime_data)

    if not extension:
        extension = '.' + mime_data.split('/').pop()

    return extension

def binaryColumnIdxs(cx_description, rows):
    binary_cols = []

    for i, x in enumerate(cx_description):

        col_name = x[0]
        driver_type = x[1]

        db_binary_type = None
        driver_binary_types = binary_type_map.keys()

        if db_binary_type in driver_binary_types:
            db_binary_type = binary_type_map[driver_type]

        if driver_type in [cx_Oracle.LONG_BINARY, cx_Oracle.BINARY, cx_Oracle.BLOB]:
            binary_cols.append(i)

    return binary_cols

def fastLobHandler(cursor, name, defaultType, size, precision, scale):

    if defaultType == cx_Oracle.CLOB:
        return cursor.var(cx_Oracle.LONG_STRING, arraysize = cursor.arraysize)
    if defaultType == cx_Oracle.BLOB:
        return cursor.var(cx_Oracle.LONG_BINARY, arraysize = cursor.arraysize)

def main():
    global DEFAULT_ARRAY
    global OUTPUT_HEADER
    global VERSION
    global NULL_AS
    global LINETERM

    license = ('CSV Exporter for Oracle v.{0}. (c) 2017 Dbvisit Software Ltd.'
               '\nThis program comes with ABSOLUTELY NO WARRANTY.\n'
               'This is free software, and you are welcome to redistribute it '
               'under\ncertain conditions.\n'
               .format(VERSION))

    # command line
    parser = argparse.ArgumentParser(
        description=(
            'CSV Exporter for Oracle v.{0}. (c) 2017 Dbvisit Software Ltd.'
            .format(VERSION)),
        prog='{0}'.format(os.path.basename(sys.argv[0])))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-s', '--schema', action='append', dest='schemas',
                       metavar='SCHEMA',
                       help=("schema name to export.  Can be specified "
                             "more than once.  For each schema a directory"
                             "will be created on the filesystem."))
    group.add_argument('-t', '--table', action='append', dest='tables',
                       metavar='TABLE',
                       help=("tables to export.  Can be specified "
                             "more than once, if no schema specified, then "
                             "tables will be exported from the current user "
                             "specified by <oracle_logon>"))
    group.add_argument('-l', '--table-list', type=argparse.FileType('r'),
                       action='store', dest='tablist',
                       metavar='FILENAME',
                       help=("file containing the list of tables for export.  "
                             "Each line may contain only one table."))
    group_sql = group.add_mutually_exclusive_group(required=False)
    group_sql.add_argument('--sql', action='store',
                           help=("SQL Statement to execute to produce CSV.  "
                                 "Data is printed to STDOUT"))
    group_sql.add_argument('-f', '--file', type=argparse.FileType('r'),
                           help=("file to read the SQL Statement from.  If "
                                 "FILE is '-' then input is read from STDIN"),)
    # parser.add_argument('-C', metavar="DIR", dest='directory', default=".",
    #                     help=("change to directory DIR.  Default - output "
    #                           "to current directory"))

    parser.add_argument('-p', '--output-path', action='store', dest='output_path',
                           help=("path to write csv data to"))
    parser.add_argument('-xc', '--exclude-column', action='append',
                        dest='exclude', metavar='COLUMN',
                        help=("specify columns to exclude. Can be specified "
                              "more than once."))
    parser.add_argument('--scn', type=int,
                        help=("specify System Change Number during exporting. "
                              "This will export data with AS OF SCN clause."))
    parser.add_argument('--null-as', type=str,
                        dest='nullas', metavar='NULL_AS',
                        help=("by default columns with NULL values exported "
                              "as nothing.  This parameter allows to override "
                              "this.  For MySQL use '\\N'"))
    parser.add_argument('--array-size', type=int,
                        help=('set the fetch buffer size. Default is: {0} rows'
                              .format(DEFAULT_ARRAY)))
    parser.add_argument('--no-header', action="store_true",
                        help=("omit header row with column names"))
    parser.add_argument('--crlf', action="store_true",
                        help=("use DOS format for line ending (\\r + \\n).  "
                              "By default, UNIX format is used (\\n)"))
    parser.add_argument('oracle_logon',
                        help=("{<username>[/<password>][@<connect_identifier>"
                              "] | / }"))
    parser.add_argument('--version', action='version',
                        version='%(prog)s v.' + VERSION)

    args = parser.parse_args()
    sys.stderr.write(license)
    try:
        conn = cx_Oracle.connect(args.oracle_logon)
    except cx_Oracle.DatabaseError:
        sys.stderr.write("Unable to connect: {0}\n".format(sys.exc_info()[1]))
        sys.exit(1)
    # initial setting
    if args.array_size:
        DEFAULT_ARRAY = args.array_size
    if args.no_header:
        OUTPUT_HEADER = False
    if args.nullas:
        NULL_AS = args.nullas
    if args.crlf:
        LINETERM = '\r\n'

    output_path = None

    if args.output_path:
        output_path = os.path.abspath(args.output_path)
    else:
        output_path = os.curdir

    conn.outputtypehandler = fastLobHandler

    # exporting
    try:
        # -o schemas
        if args.schemas is not None:
            for schema in args.schemas:
                exp_schema(conn, schema, args.scn, args.exclude, output_path)
        # -t tables
        elif args.tables is not None:
            for table in args.tables:
                exp_table(conn, table, args.scn, args.exclude, output_path)
        # -l filename
        elif args.tablist is not None:
            for table in args.tablist:
                exp_table(conn, table.strip('\n'), args.scn, args.exclude, output_path)
        # -s sql
        elif args.sql is not None:
            exp_sql(conn, sys.stdout, args.sql)
        # -f file
        elif args.file is not None:
            stmt = args.file.read()
            exp_sql(conn, sys.stdout, stmt)
    except:
        conn.close()
        raise

    conn.close()


if __name__ == '__main__':
    main()
