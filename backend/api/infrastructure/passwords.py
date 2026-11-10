import asyncio
import hashlib

from argon2 import exceptions as argon_errors
import argon2


PASSWORD_HASHER = argon2.PasswordHasher(type=argon2.Type.ID)
DUMMY_HASH = '$argon2id$v=19$m=65536,t=3,p=4$CYdF1HVEstLiedpP1WwIwA$ZvuoOSpSdFpGomSaGmjstxx+eDgHE/BeB8vAT+/6iqc'


async def hash_password(password):
    return await asyncio.to_thread(PASSWORD_HASHER.hash, password)


async def verify_password(encoded, password):
    try:
        return await asyncio.to_thread(PASSWORD_HASHER.verify, encoded, password)
    except argon_errors.VerifyMismatchError:
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def needs_rehash(encoded):
    return PASSWORD_HASHER.check_needs_rehash(encoded)
