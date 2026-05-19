"""Access key tools for Semaphore MCP.

Provides tools for managing access keys (key store) in SemaphoreUI projects.
Access keys are used for repository authentication and can be of type:
- "none": For public repositories (no credentials needed)
- "ssh": For SSH key authentication
- "login_password": For username/password authentication
"""

from typing import Any, Optional

from .base import BaseTool

VALID_ACCESS_KEY_TYPES = {"none", "ssh", "login_password"}
VALID_ACCESS_KEY_SORTS = {"name", "type"}
VALID_SORT_ORDERS = {"asc", "desc"}


class AccessKeyTools(BaseTool):
    """Tools for managing Semaphore access keys (key store)."""

    def _validate_key_type(self, key_type: str) -> None:
        if key_type not in VALID_ACCESS_KEY_TYPES:
            valid = ", ".join(sorted(VALID_ACCESS_KEY_TYPES))
            raise ValueError(f"key_type must be one of: {valid}")

    def _validate_list_options(self, sort: str, order: str) -> None:
        if sort not in VALID_ACCESS_KEY_SORTS:
            valid = ", ".join(sorted(VALID_ACCESS_KEY_SORTS))
            raise ValueError(f"sort must be one of: {valid}")
        if order not in VALID_SORT_ORDERS:
            valid = ", ".join(sorted(VALID_SORT_ORDERS))
            raise ValueError(f"order must be one of: {valid}")

    async def list_access_keys(
        self,
        project_id: int,
        key_type: Optional[str] = None,
        sort: str = "name",
        order: str = "asc",
    ) -> dict[str, Any]:
        """List all access keys for a project.

        Args:
            project_id: ID of the project
            key_type: Optional key type filter ("none", "ssh", or "login_password")
            sort: Sort field ("name" or "type")
            order: Sort order ("asc" or "desc")

        Returns:
            Dictionary containing list of access keys
        """
        try:
            if key_type is not None:
                self._validate_key_type(key_type)
            self._validate_list_options(sort, order)
            keys = self.semaphore.list_access_keys(project_id, key_type, sort, order)
            return {"access_keys": keys}
        except Exception as e:
            self.handle_error(e, f"listing access keys for project {project_id}")

    async def get_access_key(self, project_id: int, key_id: int) -> dict[str, Any]:
        """Get an access key by ID.

        Args:
            project_id: ID of the project
            key_id: ID of the access key

        Returns:
            Access key details
        """
        try:
            return self.semaphore.get_access_key(project_id, key_id)
        except Exception as e:
            self.handle_error(e, f"getting access key {key_id} in project {project_id}")

    async def create_access_key(
        self,
        project_id: int,
        name: str,
        key_type: str,
        login: Optional[str] = None,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new access key.

        Args:
            project_id: ID of the project
            name: Name for the access key
            key_type: Type of key - one of:
                - "none": For public repositories (no credentials needed)
                - "ssh": For SSH key authentication
                - "login_password": For username/password authentication
            login: Username (for ssh or login_password types)
            password: Password (for login_password type)
            private_key: Private key content (for ssh type)

        Returns:
            Created access key details
        """
        try:
            self._validate_key_type(key_type)
            return self.semaphore.create_access_key(
                project_id, name, key_type, login, password, private_key
            )
        except Exception as e:
            self.handle_error(
                e, f"creating access key '{name}' in project {project_id}"
            )

    async def update_access_key(
        self,
        project_id: int,
        key_id: int,
        name: Optional[str] = None,
        key_type: Optional[str] = None,
        login: Optional[str] = None,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
        override_secret: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Update an existing access key.

        Args:
            project_id: ID of the project
            key_id: ID of the access key
            name: New access key name (optional)
            key_type: New key type (optional)
            login: Username for ssh or login_password keys (optional)
            password: Password for login_password keys (optional)
            private_key: Private key for ssh keys (optional)
            override_secret: Force updating stored secret material (optional)

        Returns:
            Empty dict on success
        """
        try:
            if key_type is not None:
                self._validate_key_type(key_type)
            if key_type == "login_password" and password is None:
                raise ValueError(
                    "password is required when changing an access key to login_password"
                )
            if key_type == "ssh" and private_key is None:
                raise ValueError(
                    "private_key is required when changing an access key to ssh"
                )
            return self.semaphore.update_access_key(
                project_id,
                key_id,
                name,
                key_type,
                login,
                password,
                private_key,
                override_secret,
            )
        except Exception as e:
            self.handle_error(
                e, f"updating access key {key_id} in project {project_id}"
            )

    async def delete_access_key(self, project_id: int, key_id: int) -> dict[str, Any]:
        """Delete an access key by ID.

        Args:
            project_id: ID of the project
            key_id: ID of the access key to delete

        Returns:
            Empty dict on success
        """
        try:
            return self.semaphore.delete_access_key(project_id, key_id)
        except Exception as e:
            self.handle_error(
                e, f"deleting access key {key_id} in project {project_id}"
            )
