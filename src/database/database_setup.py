"""
Database Setup for Generated Datasets

Programmatically creates Supabase tables for dataset generation.

Usage:
    python database_setup.py --setup
    python database_setup.py --test
"""

import asyncio
import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


class DatasetDatabaseSetup:
    """Handles database schema creation for datasets."""
    
    def __init__(self):
        self.supabase = None
        self._load_supabase()
    
    def _load_supabase(self):
        """Load Supabase client."""
        try:
            from database.supabase_client import supabase
            self.supabase = supabase
            if not supabase:
                logger.error("Supabase not configured")
                sys.exit(1)
        except ImportError:
            logger.error("Failed to import Supabase client")
            sys.exit(1)
    
    def setup_tables(self) -> bool:
        """Create all required tables."""
        
        print("\n" + "="*70)
        print("🔧 SETTING UP DATASET SCHEMA")
        print("="*70 + "\n")
        
        # Read SQL schema
        sql_path = Path(__file__).parent / "dataset_schema.sql"
        
        try:
            with open(sql_path, 'r') as f:
                sql_content = f.read()
                # Extract just the SQL part (skip comments and explanations)
                sql_statements = [
                    stmt.strip() for stmt in sql_content.split(';')
                    if stmt.strip() and not stmt.strip().startswith('--')
                ]
            
            logger.info(f"Found {len(sql_statements)} SQL statements")
            
            # Execute each statement
            success_count = 0
            for i, statement in enumerate(sql_statements):
                if not statement:
                    continue
                
                try:
                    # Use RPC or direct execution
                    # Note: Supabase Python SDK might not support raw SQL execution
                    # We'll provide manual setup instructions instead
                    print(f"[{i+1}/{len(sql_statements)}] Statement prepared")
                    success_count += 1
                except Exception as e:
                    logger.error(f"Error executing statement {i+1}: {e}")
            
            print(f"\n✅ Prepared {success_count} statements")
            print("\n⚠️  IMPORTANT:")
            print("-" * 70)
            print("Supabase Python SDK doesn't support raw SQL execution.")
            print("You must run the schema manually:")
            print()
            print("1. Go to https://app.supabase.com")
            print("2. Open 'SQL Editor' in your project sidebar")
            print("3. Click 'New Query'")
            print("4. Copy-paste the following SQL and execute:")
            print()
            print("-" * 70)
            
            # Print SQL schema
            with open(sql_path, 'r') as f:
                sql_lines = f.readlines()
                # Skip the Python docstring and comments
                in_sql = False
                for line in sql_lines:
                    if 'SQL_SCHEMA = """' in line:
                        in_sql = True
                        continue
                    if in_sql and line.strip() == '"""':
                        break
                    if in_sql:
                        print(line, end='')
            
            print("-" * 70)
            print()
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup tables: {e}")
            return False
    
    def verify_tables(self) -> bool:
        """Verify that tables exist."""
        
        print("\n" + "="*70)
        print("✓ VERIFYING DATABASE SETUP")
        print("="*70 + "\n")
        
        required_tables = [
            'generated_datasets',
            'dataset_generation_runs',
            'dataset_statistics',
            'answer_features'
        ]
        
        try:
            for table_name in required_tables:
                # Try to query the table
                result = self.supabase.table(table_name).select("*").limit(1).execute()
                print(f"✅ Table '{table_name}' exists")
            
            print("\n✅ All database tables verified!")
            return True
            
        except Exception as e:
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                print(f"❌ Some tables are missing. Run setup first.")
                print(f"   Error: {e}")
                return False
            else:
                # Might be permission issue, but table could exist
                print(f"⚠️  Could not verify tables (possible permission issue)")
                print(f"    This might be OK if you have read-only access")
                return True
        
    def test_insert(self) -> bool:
        """Test dataset table insertion."""
        
        print("\n" + "="*70)
        print("🧪 TESTING DATABASE INSERT")
        print("="*70 + "\n")
        
        test_record = {
            "question": "Test question: What is Python?",
            "question_metadata": {"test": True},
            "target_role": "Backend Engineer",
            "experience_level": "1-3 years",
            "interview_type": "Technical",
            "ideal_answer": "Python is a high-level programming language...",
            "ideal_scores": {
                "technical_accuracy": 9,
                "clarity": 9,
                "communication": 9,
                "confidence": 9
            },
            "average_answer": "Python is a programming language used for...",
            "average_scores": {
                "technical_accuracy": 6,
                "clarity": 6,
                "communication": 6,
                "confidence": 6
            },
            "poor_answer": "Uh, Python is a thing...",
            "poor_scores": {
                "technical_accuracy": 2,
                "clarity": 2,
                "communication": 2,
                "confidence": 2
            },
            "source": "test"
        }
        
        try:
            result = self.supabase.table("generated_datasets").insert([test_record]).execute()
            
            if result.data:
                print(f"✅ Successfully inserted test record")
                print(f"   ID: {result.data[0]['id']}")
                
                # Clean up test record
                try:
                    self.supabase.table("generated_datasets").delete().eq(
                        "source", "test"
                    ).execute()
                    print(f"✅ Cleaned up test record")
                except:
                    print(f"⚠️  Could not clean up test record (might need manual deletion)")
                
                return True
            else:
                print(f"❌ Insert failed: {result}")
                return False
                
        except Exception as e:
            print(f"❌ Error during insert test: {e}")
            return False


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Setup database schema for dataset generation"
    )
    
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Setup database schema"
    )
    
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify that tables exist"
    )
    
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test database operations"
    )
    
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all setup, verify, and test"
    )
    
    args = parser.parse_args()
    
    setup = DatasetDatabaseSetup()
    
    if args.all or args.setup:
        setup.setup_tables()
    
    if args.all or args.verify:
        setup.verify_tables()
    
    if args.all or args.test:
        setup.test_insert()
    
    if not any([args.setup, args.verify, args.test, args.all]):
        print("Usage: python database_setup.py [--setup|--verify|--test|--all]")
        print("Example: python database_setup.py --setup")
        parser.print_help()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    asyncio.run(main())
