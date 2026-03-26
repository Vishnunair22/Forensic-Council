import os
import re

d = r'd:\Forensic Council\frontend\src'
props_to_remove = {'animate', 'initial', 'transition', 'exit', 'variants', 'whileHover', 'whileTap', 'whileInView', 'viewport', 'layoutId', 'layout'}

for r, ds, fs in os.walk(d):
    for f in fs:
        if f.endswith('.tsx') or f.endswith('.ts'):
            p = os.path.join(r, f)
            with open(p, 'r', encoding='utf-8') as file:
                code = file.read()
            
            original_code = code

            # Remove imports
            code = re.sub(r'import\s+\{[^\}]*\}\s+from\s+["\']framer-motion["\'];?\s*', '', code)
            
            # Replace motion namespace
            code = re.sub(r'<motion\.([a-zA-Z0-9_]+)', r'<\1', code)
            code = re.sub(r'</motion\.([a-zA-Z0-9_]+)>', r'</\1>', code)
            
            # AnimatePresence to React Fragment
            code = re.sub(r'<AnimatePresence[^>]*>', '<>', code)
            code = code.replace('</AnimatePresence>', '</>')

            # Smart prop removal using stack
            out = []
            i = 0
            while i < len(code):
                # Check if we hit a prop to remove
                match = None
                if code[i-1].isspace() if i > 0 else True:
                    for prop in props_to_remove:
                        if code.startswith(prop, i):
                            # Ensure it's not a substring of another word
                            end_of_prop = i + len(prop)
                            if end_of_prop < len(code) and (code[end_of_prop].isspace() or code[end_of_prop] == '=' or code[end_of_prop] in ['>', '/']):
                                match = prop
                                break
                
                if match:
                    # Check if it has an assignment
                    assignment_idx = code.find('=', i, i + len(match) + 5)
                    has_assignment = False
                    if assignment_idx != -1 and code[i+len(match):assignment_idx].strip() == '':
                        has_assignment = True

                    if has_assignment:
                        # Parse the prop value
                        idx = assignment_idx + 1
                        while idx < len(code) and code[idx].isspace(): idx += 1
                        
                        if code[idx] == '{':
                            # Brace matching
                            depth = 1
                            idx += 1
                            while idx < len(code) and depth > 0:
                                if code[idx] == '{': depth += 1
                                elif code[idx] == '}': depth -= 1
                                idx += 1
                        elif code[idx] in ['"', "'"]:
                            # Quote matching
                            quote = code[idx]
                            idx += 1
                            while idx < len(code) and code[idx] != quote:
                                if code[idx] == '\\': idx += 2
                                else: idx += 1
                            idx += 1
                        else:
                            # Simple word prop
                            while idx < len(code) and not code[idx].isspace() and code[idx] not in ['>', '/']:
                                idx += 1
                        i = idx # Skip the prop
                    else:
                        # Boolean prop, just skip the name
                        i += len(match)
                else:
                    out.append(code[i])
                    i += 1
                    
            new_code = "".join(out)
            
            if new_code != original_code:
                with open(p, 'w', encoding='utf-8') as file:
                    file.write(new_code)
                print(f"Cleaned {f}")
