"""Create a Gemini-compatible vectors API index without changing existing indexes."""
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec


def ensure_index(client, name):
    if name in client.list_indexes().names():
        info = client.describe_index(name)
        if (info.dimension != 768 or info.metric != 'cosine'
                or getattr(info, 'embed', None)):
            raise ValueError('Existing index is incompatible; nothing was changed. Use a new name.')
        print(f'Index {name} already exists: 768 dimensions, cosine. Nothing changed.')
        return
    client.create_index(name=name, dimension=768, metric='cosine', vector_type='dense',
                        spec=ServerlessSpec(cloud='aws', region='us-east-1'), timeout=60)
    print(f'Created {name}: 768 dimensions, cosine. Existing indexes were preserved.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', default='pdf-gemini-768')
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parent / '.env')
    key = os.getenv('PIPECONE_API_KEY')
    if not key:
        parser.exit(1, 'Missing PIPECONE_API_KEY in environment or .env.\n')
    try:
        ensure_index(Pinecone(api_key=key), args.name)
    except ValueError as error:
        parser.exit(1, f'{error}\n')
    except Exception as error:
        # Do not print credentials or SDK request headers.
        status = getattr(error, 'status', None)
        parser.exit(1, f'Pinecone operation failed ({type(error).__name__}, HTTP {status}). '
                    'Check key permissions, index quota, and connectivity in Pinecone. '
                    'If creation timed out, check the console before retrying.\n')


if __name__ == '__main__':
    main()
