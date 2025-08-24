import sys
from passlib.context import CryptContext

# This uses the same context as the main application's auth
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def main():
    if len(sys.argv) < 2:
        print("Usage: python hash_password.py <your_password_here>")
        sys.exit(1)

    password = sys.argv[1]
    hashed_password = pwd_context.hash(password)

    print("\n--- Superuser Password Hash ---")
    print("Copy the following hash into your superuser.json file:")
    print(f"\n{hashed_password}\n")

if __name__ == "__main__":
    main()
