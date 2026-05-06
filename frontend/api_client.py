import httpx
import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import datetime

class ApiClient:
    def __init__(self, base_url: str = "http://localhost:8000/api"):
        self.base_url = base_url

    def get_accounts(self) -> List[Dict[str, Any]]:
        try:
            response = httpx.get(f"{self.base_url}/accounts/")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching accounts: {e}")
            return []

    def create_account(self, data: Dict[str, Any]) -> Dict[str, Any]:
        response = httpx.post(f"{self.base_url}/accounts/", json=data)
        response.raise_for_status()
        return response.json()

    def get_credits(self) -> List[Dict[str, Any]]:
        try:
            response = httpx.get(f"{self.base_url}/credits/")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching credits: {e}")
            return []

    def get_transactions(self) -> List[Dict[str, Any]]:
        try:
            response = httpx.get(f"{self.base_url}/transactions/")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching transactions: {e}")
            return []

    def create_transaction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        response = httpx.post(f"{self.base_url}/transactions/", json=data)
        response.raise_for_status()
        return response.json()

    def create_credit(self, data: Dict[str, Any]) -> Dict[str, Any]:
        response = httpx.post(f"{self.base_url}/credits/", json=data)
        response.raise_for_status()
        return response.json()

    def bulk_create_transactions(self, transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for tx in transactions:
            try:
                results.append(self.create_transaction(tx))
            except Exception as e:
                print(f"Error creating transaction in bulk: {e}")
        return results

    def bulk_create_credits(self, credits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for cr in credits:
            try:
                results.append(self.create_credit(cr))
            except Exception as e:
                print(f"Error creating credit in bulk: {e}")
        return results
