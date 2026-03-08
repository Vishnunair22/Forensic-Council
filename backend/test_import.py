import traceback
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

with open("import_error.txt", "w") as f:
    try:
        import infra.postgres_client
        f.write("Import successful!\n")
    except Exception as e:
        f.write("Exception caught:\n")
        traceback.print_exc(file=f)
