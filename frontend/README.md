# Frontend - Forensic Council

> ⚠️ **Security Note (March 2026):**
> This project uses Next.js 15.3.3 which has a known vulnerability (CVE-2025-66478).
> Run `npm audit` for details and upgrade when a patched version is available.

Modern Next.js frontend for the Forensic Council multi-agent forensic analysis system.

## Quick Start

### Prerequisites
- Node.js 18+ 
- npm or yarn
- API running on `localhost:8000` (or configured in environment)

### Installation

```bash
# Install dependencies
npm install

# Create .env.local file with configuration
cp .env.example .env.local
```

### Environment Variables

```env
# API Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000

# Optional: Internal API URL for server-side rendering
INTERNAL_API_URL=http://backend:8000
```

### Development

```bash
# Start development server
npm run dev

# Open browser
open http://localhost:3000
```

### Production Build

```bash
# Build for production
npm run build

# Start production server
npm start
```

---

## Project Structure

```
frontend/
├── src/
│   ├── app/                    # Next.js pages and routes
│   ├── components/             # Reusable React components
│   │   ├── evidence/          # Evidence page components
│   │   └── ui/                # UI building blocks
│   ├── hooks/                 # Custom React hooks
│   ├── lib/                   # Utility functions
│   └── types/                 # TypeScript definitions
├── public/                    # Static assets
├── ARCHITECTURE.md            # Component architecture guide
├── COMPONENTS.md              # Component reference
└── README.md                  # This file
```

### Key Directories

#### `src/app/`
Next.js App Router pages:
- `page.tsx` - Landing page
- `evidence/page.tsx` - Investigation page
- `result/page.tsx` - Results page
- `session-expired/page.tsx` - Auth timeout page
- `api/` - API routes

#### `src/components/evidence/`
Modular components for the evidence page:
- `HeaderSection.tsx` - Page header
- `FileUploadSection.tsx` - File upload form
- `AgentProgressDisplay.tsx` - Agent analysis display
- `CompletionBanner.tsx` - Completion message
- `ErrorDisplay.tsx` - Error handler
- `HITLCheckpointModal.tsx` - Human-in-the-loop modal

#### `src/components/ui/`
Reusable UI components:
- `dialog.tsx` - Dialog/modal wrapper
- `AgentIcon.tsx` - Agent icons
- `AgentResponseText.tsx` - Agent response formatter

#### `src/hooks/`
Custom React hooks:
- `useForensicData.ts` - Forensic data management
- `useSimulation.ts` - Investigation simulation
- `useSound.ts` - Sound effects

#### `src/lib/`
Utility modules:
- `api.ts` - Backend API client
- `constants.ts` - App constants
- `schemas.ts` - Data validation
- `utils.ts` - Helper functions

---

## Development Workflow

### Component Development

1. **Create Component**
   ```typescript
   // src/components/MyComponent.tsx
   interface MyComponentProps {
     title: string;
     onAction: () => void;
   }
   
   export function MyComponent({ title, onAction }: MyComponentProps) {
     return (
       <div className="...">
         {title}
         <button onClick={onAction}>Action</button>
       </div>
     );
   }
   ```

2. **Add to Index** (if in a directory)
   ```typescript
   // src/components/evidence/index.ts
   export { MyComponent } from "./MyComponent";
   ```

3. **Use in Page**
   ```typescript
   import { MyComponent } from "@/components/evidence";
   
   export default function Page() {
     return <MyComponent title="Test" onAction={() => {}} />;
   }
   ```

### Component Organization

**Single File Components:**
- Smaller, self-contained components
- Simple presentation logic
- Located in `components/` or `components/ui/`

**Feature Component Directories:**
- Related components grouped together
- Shared types and utilities
- Example: `components/evidence/`

**Page Components:**
- Orchestrate entire page
- Import feature components
- Handle page-level state
- Located in `app/*/page.tsx`

---

## Styling

### Tailwind CSS

All styling uses Tailwind's core utilities:

```typescript
<div className="flex items-center justify-between p-4 rounded-lg bg-white/5 border border-white/10">
  Content
</div>
```

### Color Scheme

```
Primary:   emerald-*   (actions, success)
Secondary: cyan-*      (information, accents)
Base:      slate-*     (text, backgrounds)
Warning:   amber-*     (warnings)
Error:     red-*       (errors)
```

### Dark Mode

App uses dark theme by default:
- Background: `#050505` (pure black)
- Cards: `white/5` to `white/10` with backdrop blur
- Text: `white` to `slate-*` shades

---

## Animation

### Framer Motion

Used for smooth animations:

```typescript
import { motion, AnimatePresence } from "framer-motion";

<motion.div
  initial={{ opacity: 0, scale: 0.95 }}
  animate={{ opacity: 1, scale: 1 }}
  exit={{ opacity: 0 }}
>
  Animated content
</motion.div>

<AnimatePresence mode="wait">
  {showContent && <YourComponent />}
</AnimatePresence>
```

### Animation Patterns

- **Page Transitions**: Fade in/out with scale
- **Loading**: Spinning icons, pulsing dots
- **Success**: Scale-up and bounce
- **Errors**: Shake or flash
- **Lists**: Staggered item entry

---

## State Management

### Client-Side State

**Component State:**
```typescript
const [file, setFile] = useState<File | null>(null);
const [isDragging, setIsDragging] = useState(false);
```

**Hook State:**
```typescript
const {
  status,
  agentUpdates,
  completedAgents,
} = useSimulation({ /* options */ });
```

**Session Storage:**
```typescript
sessionStorage.setItem("key", value);
const value = sessionStorage.getItem("key");
```

### Data Flow

```
Page Component
  ├── State (useState)
  ├── Hooks (useSimulation, useForensicData)
  ├── Callbacks (useCallback)
  └── Effects (useEffect)
    └── Child Components (receive via props)
```

---

## API Integration

### Authentication

```typescript
import { ensureAuthenticated, getAuthToken } from "@/lib/api";

// Auto-login if needed
const token = await ensureAuthenticated();

// Get current token
const token = getAuthToken();
```

### Calling API

```typescript
import { startInvestigation, getReport } from "@/lib/api";

// Start investigation
const response = await startInvestigation(file, caseId, investigatorId);

// Get report
const report = await getReport(sessionId);
```

### WebSocket Connection

```typescript
const { connectWebSocket } = useSimulation({
  playSound: () => {},
  onComplete: () => {},
});

await connectWebSocket(sessionId);
```

---

## Testing

### Run Tests

```bash
# Run all tests
npm test

# Watch mode
npm test:watch

# Coverage report
npm test:coverage
```

### Test Files

```
src/__tests__/
├── hooks/
│   ├── useForensicData.test.ts
│   └── useSimulation.test.ts
├── lib/
│   ├── api.test.ts
│   └── schemas.test.ts
└── types/
    └── schema.test.ts
```

### Writing Tests

```typescript
import { render, screen } from "@testing-library/react";
import { MyComponent } from "@/components/MyComponent";

describe("MyComponent", () => {
  it("renders with title", () => {
    render(<MyComponent title="Test" onAction={() => {}} />);
    expect(screen.getByText("Test")).toBeInTheDocument();
  });
});
```

---

## Code Quality

### Linting

```bash
# Run ESLint
npm run lint

# Fix linting issues
npm run lint:fix
```

### Type Checking

```bash
# Check TypeScript
npm run type-check
```

### Code Style

- Semicolons required
- 2-space indentation
- Double quotes for strings
- Trailing commas in multiline objects

---

## Performance

### Optimization Techniques

1. **Code Splitting**
   - Next.js automatically splits at page boundaries
   - Use dynamic imports for heavy components

2. **Image Optimization**
   - Use Next.js Image component
   - Optimize file previews (compress before display)

3. **Memoization**
   ```typescript
   const memoValue = useMemo(() => expensiveCalc(), [deps]);
   const memoCallback = useCallback(() => doSomething(), [deps]);
   ```

4. **Resource Cleanup**
   ```typescript
   useEffect(() => {
     const url = URL.createObjectURL(file);
     return () => URL.revokeObjectURL(url);
   }, [file]);
   ```

### Bundle Analysis

```bash
# Analyze bundle size
npm run build -- --analyze
```

---

## Accessibility

### Best Practices

1. **Semantic HTML**
   - Use proper heading levels
   - Use `<button>` for buttons, not `<div>`
   - Use labels for form inputs

2. **ARIA Labels**
   ```typescript
   <button aria-label="Upload evidence file">
     <UploadIcon />
   </button>
   ```

3. **Keyboard Navigation**
   - All interactive elements keyboard accessible
   - Tab order logical
   - Focus visible

4. **Color Contrast**
   - Text passes WCAG AA standards
   - Don't rely on color alone

### Testing Accessibility

```bash
npm install --save-dev @axe-core/react
```

---

## Debugging

### Development Tools

1. **React DevTools**
   - Chrome/Firefox browser extension
   - Inspect component props and state

2. **Next.js DevTools**
   - Built-in error overlay
   - Source maps for debugging

3. **Console Logging**
   ```typescript
   console.log("Debug info:", data);
   console.error("Error occurred", error);
   ```

### Common Issues

**Issue: File upload not working**
- Check API endpoint configuration
- Verify session storage
- Check browser console for errors

**Issue: Agent updates not showing**
- Verify WebSocket connection
- Check network tab for messages
- Review useSimulation hook

**Issue: Styling looks wrong**
- Clear browser cache
- Rebuild Tailwind: `npm run build`
- Check for CSS conflicts

---

## Deployment

### Environment Setup

```env
# .env.production
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
```

### Docker

```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
```

### Vercel

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel
```

### Manual Deployment

```bash
# Build
npm run build

# Start
npm start
```

---

## Useful Commands

```bash
# Development
npm run dev              # Start dev server
npm run build           # Build for production
npm start               # Start production server

# Quality
npm run lint            # Check code style
npm run lint:fix        # Fix style issues
npm run type-check      # Type checking
npm test                # Run tests
npm run test:watch      # Watch mode
npm run test:coverage   # Coverage report

# Maintenance
npm install             # Install dependencies
npm update              # Update dependencies
npm audit               # Check security issues
```

---

## Documentation

### Key Documents

- **ARCHITECTURE.md** - Component structure and hierarchy
- **COMPONENTS.md** - Component reference and usage
- **README.md** - This file

### Related Documentation

- Backend: `../backend/README.md`
- API Documentation: `../docs/API.md`
- Deployment: `../docs/docker/DOCKER_BUILD.md`

---

## Contributing

### Getting Started

1. Create feature branch
2. Make changes
3. Test thoroughly
4. Update documentation
5. Submit pull request

### Code Standards

- Follow existing patterns
- Use TypeScript for new code
- Add JSDoc comments
- Test changes
- Update related docs

### Component Checklist

- [ ] Component file created with proper structure
- [ ] Props interface defined
- [ ] JSDoc comments added
- [ ] Tailwind styling applied
- [ ] Accessibility features included
- [ ] Component exported from index
- [ ] Tests written
- [ ] Documentation updated

---

## Resources

### Documentation
- [Next.js Docs](https://nextjs.org/docs)
- [React Docs](https://react.dev)
- [Tailwind CSS](https://tailwindcss.com)
- [Framer Motion](https://www.framer.com/motion)
- [TypeScript Handbook](https://www.typescriptlang.org/docs)

### Tools
- [ESLint](https://eslint.org)
- [Prettier](https://prettier.io)
- [Jest](https://jestjs.io)
- [React Testing Library](https://testing-library.com)

---

## Troubleshooting

### Development Server Issues

**Port already in use:**
```bash
# Use different port
npm run dev -- -p 3001
```

**Module not found:**
```bash
# Clear .next cache
rm -rf .next
npm run dev
```

**Build failures:**
```bash
# Clean install
rm -rf node_modules package-lock.json
npm install
npm run build
```

### Production Issues

**Slow page load:**
- Check bundle size
- Optimize images
- Enable caching

**Memory issues:**
- Monitor with `top` or Task Manager
- Check for memory leaks
- Review logs

---

## Support

For issues and questions:
1. Check existing documentation
2. Review troubleshooting section
3. Check GitHub issues
4. Contact the team

---

## License

MIT - See LICENSE file for details

---

**Version:** 1.0.0  
**Last Updated:** March 8, 2026  
**Maintainers:** Forensic Council Team
