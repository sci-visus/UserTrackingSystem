#!/usr/bin/env python3
"""
Generate secure tokens for users.
Run this script to generate new tokens for your .env file.
"""

import uuid


def generate_user_tokens(num_users=12):
    """Generate unique UUID tokens for users"""
    tokens = []
    
    print(f"Generating {num_users} secure tokens...\n")
    
    for i in range(1, num_users + 1):
        token = str(uuid.uuid4())
        tokens.append(f"user{i}:{token}")
    
    # Output for .env file
    print("=" * 80)
    print("Add this line to your .env file:")
    print("=" * 80)
    env_line = f"USER_TOKENS={','.join(tokens)}"
    print(env_line)
    print()
    
    # Output individual user access URLs
    print("=" * 80)
    print("User Access URLs:")
    print("=" * 80)
    
    for token_pair in tokens:
        user_id, token = token_pair.split(':', 1)
        print(f"{user_id:8s}: http://localhost:10333/annotation_tool?token={token}")
    
    print("\n" + "=" * 80)
    print("IMPORTANT SECURITY NOTES:")
    print("=" * 80)
    print("1. Keep these tokens secure - treat them like passwords")
    print("2. Share each URL only with its designated user")
    print("3. Tokens are cryptographically random (UUID4)")
    print("4. To revoke access, remove the token from USER_TOKENS and restart")
    print("5. Sessions expire after SESSION_TIMEOUT (default: 3600 seconds)")
    print("=" * 80)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate secure tokens for annotation tool users')
    parser.add_argument('-n', '--num-users', type=int, default=12,
                       help='Number of user tokens to generate (default: 12)')
    
    args = parser.parse_args()
    
    generate_user_tokens(args.num_users)
