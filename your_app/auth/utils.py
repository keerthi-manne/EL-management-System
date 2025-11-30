import bcrypt

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def check_password(stored_hash, password_attempt):
    # Convert hex string to bytes if necessary
    if isinstance(stored_hash, str):
        # If it starts with '0x', it's hex representation from DB
        if stored_hash.startswith('0x') or stored_hash.startswith('0X'):
            stored_hash = bytes.fromhex(stored_hash[2:])
        else:
            stored_hash = stored_hash.encode('utf-8')
    return bcrypt.checkpw(password_attempt.encode('utf-8'), stored_hash)

