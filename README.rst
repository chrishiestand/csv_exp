=====================================
``csv_exp`` — CSV Exporter for Oracle
=====================================

The sole purpose of this tool is to provide a convenient way to export data
from Oracle tables into CSV format.

PLEASE NOTE that this program is a free software released under the *GPL v.3*
(Licence) and is comes without warranty and is not covered by Dbvisit Software
Support Agreement and as per clauses 15 and 16 of the Licence - any of the
issues that might result out of the use or inability to use of this program
will not be handled by Dbvisit Support Team, and that Dbvisit Software will
not be liable to you for damages, including any general, special, incidental
or consequential damages arising out of the use or inability to use the
program (including but not limited to loss of data or data being rendered
inaccurate or losses sustained by you or third parties or a failure of the
program to operate with any other programs).

However you can log issues on the Issues page of this Github repository or more
than welcomed to  to contribute and make modifications or improvements to the
code.

Run with ``-h`` parameter to see the help screen::
  
  usage: csv_exp [-h] (-s SCHEMA | -t TABLE | [--sql SQL | -f FILE] [-xc COLUMN]
                 [--scn SCN] [--null-as NULL_AS] [--array-size ARRAY_SIZE]
                 [--no-header] [--crlf] [--version]
                 oracle_logon
  
  CSV Exporter for Oracle v.0.2. (c) 2017 Dbvisit Software Ltd.
  
  positional arguments:
    oracle_logon          {<username>[/<password>][@<connect_identifier>] | / }
  
  optional arguments:
    -h, --help            show this help message and exit
    -s SCHEMA, --schema SCHEMA
                          schema name to export. Can be specified more than
                          once. For each schema a directorywill be created on
                          the filesystem.
    -t TABLE, --table TABLE
                          tables to export. Can be specified more than once, if
                          no schema specified, then tables will be exported from
                          the current user specified by <oracle_logon>
    --sql SQL             SQL Statement to execute to produce CSV. Data is
                          printed to STDOUT
    -f FILE, --file FILE  file to read the SQL Statement from. If FILE is '-'
                          then input is read from STDIN
    -xc COLUMN, --exclude-column COLUMN
                          specify columns to exclude. Can be specified more than
                          once.
    --scn SCN             specify System Change Number during exporting. This
                          will export data with AS OF SCN clause.
    --null-as NULL_AS     by default columns with NULL values exported as
                          nothing. This parameter allows to override this. For
                          MySQL use '\N'
    --array-size ARRAY_SIZE
                          set the fetch buffer size. Default is: 16384 rows
    --no-header           omit header row with column names
    --crlf                use DOS format for line ending (\r + \n). By default,
                          UNIX format is used (\n)
    --version             show program's version number and exit

Installation and Usage
----------------------
Make sure that you have the ``cx_Oracle`` module installed. If not - 
run ``easy_install cx_Oracle`` or ``pip install cx_Oracle`` depending
on the package manager installed on your system as csv_exp depends on it.

Then just copy ``csv_exp.py`` somewhere accessisble, like your ``~/bin`` folder 
or ``/usr/local/bin``.

Examples
--------

- Export whole schema. This will create a number of ``SCHEMA.*.csv`` files in
  the current directory::
    
    csv_exp.py -s SCHEMA user/pwd@ORCL

- Exporting several tables (assuming that user ``scott`` has grant to select
  from ``SCHEMA1``)::

    csv_exp.py -t TABLE1 -t SCHEMA1.TABLE4 scott/tiger@ORCL

- Exporting the result of SQL execution. Result of ``--sql`` are not being 
  saved to any file, but output to STDOUT by default, so you'll need to
  redirect the output somewhere::

    csv_exp.py --sql "SELECT * FROM SCHEMA.MY_VIEW" scott/tiger > output.csv

