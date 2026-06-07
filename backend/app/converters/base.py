from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseConverter(ABC):
    def __init__(self, file_path: str):
        self.file_path = file_path

    @abstractmethod
    def detect_tables(self) -> List[Dict[str, Any]]:
        """
        Scan the file and return a list of dictionaries with table information:
        [
            {
                "name": str,
                "columns": [{"name": str, "type": str}],
                "estimated_rows": int
            }
        ]
        """
        pass

    @abstractmethod
    def get_preview(self, table_name: str, limit: int = 10) -> Dict[str, Any]:
        """
        Return the preview data for a table:
        {
            "columns": [str],
            "rows": [List[Any]]
        }
        """
        pass

    @abstractmethod
    def convert(self, db_path: str, table_mappings: Dict[str, str]) -> List[str]:
        """
        Write the tables to the target DuckDB database at db_path.
        table_mappings maps original table names to user-defined names.
        Returns a list of tables successfully written.
        """
        pass
