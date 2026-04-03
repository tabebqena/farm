import sqlite3
import sys


def empty_table(database_file, table_name):
    """
    Empties all data from the specified SQLite table.

    Args:
        database_file (str): The path to the SQLite database file.
        table_name (str): The name of the table to empty.
    """
    connection = None
    try:
        # Connect to the SQLite database
        connection = sqlite3.connect(database_file)
        cursor = connection.cursor()
        print(f"Connected to SQLite database: {database_file}")

        # SQL statement to delete all rows from the table
        # Note: SQLite does not support TRUNCATE TABLE, so DELETE FROM is used.
        delete_query = f"DELETE FROM {table_name}"

        # Execute the query
        cursor.execute(delete_query)

        # Commit the changes to the database
        connection.commit()
        print(f"All rows deleted from the table '{table_name}' successfully.")

        # Optional: Reset the auto-increment counter (specific to SQLite)
        # This makes the next inserted row start its ID from 1 again
        reset_autoincrement_query = (
            f"DELETE FROM sqlite_sequence WHERE name='{table_name}'"
        )
        cursor.execute(reset_autoincrement_query)
        connection.commit()
        print("Auto-increment counter reset.")

        # Optional: Use VACUUM to reclaim space (deletes can leave empty space)
        cursor.execute("VACUUM")
        connection.commit()
        print("Database vacuumed to reclaim space.")

    except sqlite3.Error as error:
        print(f"Error emptying table: {error}")
        if connection:
            connection.rollback()  # Roll back changes if an error occurs
    finally:
        if connection:
            connection.close()
            print("The SQLite connection is closed.")


# --- Usage Example ---
if __name__ == "__main__":
    table_name = sys.argv[1]
    db_name = sys.argv[2] if len(sys.argv) > 2 else "db.sqlite3"

    # Replace 'my_database.db' with your database file path
    # Replace 'my_table' with the name of your table
    empty_table(db_name, table_name)
