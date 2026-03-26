import os
import re

directory = r"d:\Forensic Council\frontend\src"

def strip_animations(content):
    # Remove module imports
    content = re.sub(r'import\s+\{[^\}]*\b(motion|AnimatePresence)\b[^\}]*\}\s+from\s+["\']framer-motion["\'];?\n?', '', content)

    # Replace tags
    tags = ['div', 'h1', 'h2', 'h3', 'p', 'span', 'button', 'img', 'video', 'svg', 'path']
    for tag in tags:
        content = content.replace(f'<motion.{tag}', f'<{tag}')
        content = content.replace(f'</motion.{tag}>', f'</{tag}>')
        
    # Animate presence to fragment
    content = re.sub(r'<AnimatePresence[^>]*>', '<>', content)
    content = content.replace('</AnimatePresence>', '</>')

    # Strip props (very basic regex, handles single brace depth well enough)
    props = ['initial', 'animate', 'exit', 'transition', 'variants', 'whileHover', 'whileInView', 'viewport', 'layoutId', 'whileTap', 'layout']
    for p in props:
        content = re.sub(rf'\b{p}=\{{(?:[^{{}}]*|\{{[^{{}}]*\}})*\}}\s*', '', content)
        # fallback for simple string props like layoutId="x"
        content = re.sub(rf'\b{p}="[^"]*"\s*', '', content)
        
    # Special fix for stray layout attribute (boolean prop)
    content = re.sub(r'\blayout\b(?=[\s>])', '', content)

    return content

count = 0
for root, dirs, files in os.walk(directory):
    for file in files:
        if file.endswith('.tsx') or file.endswith('.ts'):
            path = os.path.join(root, file)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            new_content = strip_animations(content)
            if new_content != content:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                count += 1
                print(f"Cleaned {file}")
print(f"Total files cleaned: {count}")
