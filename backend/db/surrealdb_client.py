# ============================================================================
# Project Panopticon - SurrealDB Client
# ============================================================================

import logging
from typing import Any, Optional, List, Dict
from surrealdb import AsyncSurreal
import structlog

log = structlog.get_logger(__name__)


class SurrealDBClient:
    """Client for SurrealDB database operations."""

    def __init__(
        self,
        url: str,
        namespace: str,
        database: str,
        user: str,
        password: str,
    ):
        """Initialize SurrealDB client.

        Args:
            url: SurrealDB WebSocket URL
            namespace: SurrealDB namespace
            database: SurrealDB database name
            user: Authentication username
            password: Authentication password
        """
        self.url = url
        self.namespace = namespace
        self.database = database
        self.user = user
        self.password = password
        self.client: Any = None
        self.connected = False

    async def connect(self) -> None:
        """Connect to SurrealDB."""
        try:
            self.client = AsyncSurreal(self.url)
            await self.client.connect()

            # Authenticate and select namespace/database
            await self.client.signin({
                "user": self.user,
                "pass": self.password,
            })
            await self.client.use(namespace=self.namespace, database=self.database)

            self.connected = True
            log.info("SurrealDB connection established")

        except Exception as e:
            log.error(f"Failed to connect to SurrealDB: {e}")
            raise

    async def close(self) -> None:
        """Close SurrealDB connection."""
        if self.client:
            await self.client.close()
            self.connected = False
            log.info("SurrealDB connection closed")

    async def query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a SurrealDB query.

        Args:
            query: SurrealDB query string
            variables: Query variables

        Returns:
            Query result
        """
        if not self.connected:
            raise RuntimeError("SurrealDB client not connected")

        try:
            result = await self.client.query(query, variables)
            log.debug(f"Query executed: {query[:100]}...")
            return result
        except Exception as e:
            log.error(f"Query execution failed: {e}")
            raise

    async def create(self, table: str, data: Dict[str, Any]) -> Any:
        """Create a new record in SurrealDB.

        Args:
            table: Table name
            data: Record data

        Returns:
            Created record
        """
        query = f"CREATE {table} CONTENT $data"
        variables = {"data": data}
        result = await self.query(query, variables)
        return result[0].result

    async def select(self, table: str, id: Optional[str] = None) -> List[Any]:
        """Select records from SurrealDB.

        Args:
            table: Table name
            id: Optional record ID

        Returns:
            Selected records
        """
        if id:
            query = f"SELECT * FROM {table} WHERE id = $id"
            variables = {"id": id}
        else:
            query = f"SELECT * FROM {table}"
            variables = None

        result = await self.query(query, variables)
        return result[0].result

    async def update(self, id: str, data: Dict[str, Any]) -> Any:
        """Update a record in SurrealDB.

        Args:
            id: Record ID
            data: Updated data

        Returns:
            Updated record
        """
        query = f"UPDATE {id} CONTENT $data"
        variables = {"data": data}
        result = await self.query(query, variables)
        return result[0].result

    async def delete(self, id: str) -> Any:
        """Delete a record from SurrealDB.

        Args:
            id: Record ID

        Returns:
            Deleted record
        """
        query = f"DELETE {id}"
        result = await self.query(query)
        return result[0].result

    async def insert(self, table: str, data: List[Dict[str, Any]]) -> List[Any]:
        """Insert multiple records into SurrealDB.

        Args:
            table: Table name
            data: List of records to insert

        Returns:
            Inserted records
        """
        query = f"INSERT INTO {table} $data"
        variables = {"data": data}
        result = await self.query(query, variables)
        return result[0].result

    async def let(self, var_name: str, value: Any) -> None:
        """Set a variable for subsequent queries.

        Args:
            var_name: Variable name
            value: Variable value
        """
        query = f"LET $var_name = $value"
        variables = {"var_name": var_name, "value": value}
        await self.query(query, variables)

    async def info(self) -> Dict[str, Any]:
        """Get database information.

        Returns:
            Database info
        """
        result = await self.query("INFO")
        return result[0].result

    async def table_exists(self, table: str) -> bool:
        """Check if a table exists.

        Args:
            table: Table name

        Returns:
            True if table exists, False otherwise
        """
        try:
            result = await self.query(f"INFO TABLE {table}")
            return len(result) > 0
        except:
            return False

    async def create_table(self, table: str) -> None:
        """Create a new table.

        Args:
            table: Table name
        """
        query = f"DEFINE TABLE {table} SCHEMAFULL"
        await self.query(query)
        log.info(f"Table created: {table}")

    async def create_field(self, table: str, field_name: str, field_type: str) -> None:
        """Create a new field in a table.

        Args:
            table: Table name
            field_name: Field name
            field_type: Field type (e.g., "string", "int", "float", "bool", "datetime", "array", "object")
        """
        query = f"DEFINE FIELD {field_name} ON {table} TYPE {field_type}"
        await self.query(query)
        log.info(f"Field created: {table}.{field_name}")

    async def create_index(self, table: str, index_name: str, fields: List[str], index_type: str = "DEFAULT") -> None:
        """Create an index on a table.

        Args:
            table: Table name
            index_name: Index name
            fields: List of field names
            index_type: Index type (DEFAULT, GEOSPATIAL, MTREE, etc.)
        """
        fields_str = ", ".join(fields)
        query = f"DEFINE INDEX {index_name} ON {table} FIELDS {fields_str} TYPE {index_type}"
        await self.query(query)
        log.info(f"Index created: {index_name} on {table}")

    async def create_relation(self, from_table: str, from_field: str, to_table: str, to_field: str) -> None:
        """Create a relation between two tables.

        Args:
            from_table: Source table
            from_field: Source field
            to_table: Target table
            to_field: Target field
        """
        query = f"DEFINE RELATION {from_table}.{from_field} ON {from_table} IN {to_table}.{to_field}"
        await self.query(query)
        log.info(f"Relation created: {from_table}.{from_field} -> {to_table}.{to_field}")