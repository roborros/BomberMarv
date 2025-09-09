# BomberMarv - Quick Start Guide

## 🚀 One-Command Setup & Run

**Just run this single command:**
```bash
python pyBomberMarv_dual.py
```

That's it! The system will:
- ✅ Automatically detect if Node.js is installed
- ✅ Install React dependencies (`npm install`)
- ✅ Build the web client (`npm run build`)
- ✅ Start both pygame window AND web server
- ✅ Open the game in your browser

## 🎮 How to Play

### Option 1: Desktop (Pygame Window)
- Use **WASD** or **Arrow Keys** to move
- Press **Space** to place bombs
- Classic local gameplay

### Option 2: Web Browser
- Open **http://localhost:8080** in any browser
- Use **WASD** keys or **touch controls** (mobile)
- Real-time multiplayer ready!

### Option 3: Both at Once!
- Both pygame and web run simultaneously
- Perfect for testing and comparison
- Same game logic, different renderers

## 📱 Mobile Support

The web version works great on phones and tablets:
- Touch controls appear automatically
- Responsive design fits any screen
- Same multiplayer experience

## ⚙️ Command Options

```bash
# Default: Both pygame + web
python pyBomberMarv_dual.py

# Only pygame (no web setup needed)
python pyBomberMarv_dual.py --pygame-only

# Only web (headless, no pygame window)
python pyBomberMarv_dual.py --web-only

# Skip automatic setup (if already done)
python pyBomberMarv_dual.py --no-auto-setup

# Just set up web client, don't run game
python pyBomberMarv_dual.py --setup-only

# Original pygame version (unchanged)
python pyBomberMarv.py
```

## 🔧 Requirements

### For Pygame (Desktop):
- Python 3.7+
- pygame (already in your project)

### For Web Client:
- **Node.js 14+** (download from [nodejs.org](https://nodejs.org/))
- That's it! Everything else is automatic.

### No Node.js?
```bash
# Run pygame only
python pyBomberMarv_dual.py --pygame-only
```

## 🐛 Troubleshooting

### "Node.js not found"
- Install Node.js from https://nodejs.org/
- Or run with `--pygame-only`

### "npm install failed"
- Check internet connection
- Try: `python pyBomberMarv_dual.py --setup-only`

### Web client not loading
- Check if http://localhost:8080 shows anything
- Try rebuilding: `python pyBomberMarv_dual.py --setup-only`

### Port already in use
- Close other applications using ports 8080 or 8765
- Or change ports in the code

## 🎯 What's Different?

| Feature | Original | New Dual System |
|---------|----------|-----------------|
| **Setup** | Ready to go | One command setup |
| **Platforms** | Desktop only | Desktop + Web + Mobile |
| **Multiplayer** | Local only | Real-time web multiplayer |
| **Testing** | Single view | Side-by-side comparison |
| **Future** | pygame only | Multiple rendering backends |

## 🚀 Next Steps

1. **Run the game**: `python pyBomberMarv_dual.py`
2. **Share with friends**: Send them http://localhost:8080
3. **Play multiplayer**: Everyone can join from their browsers
4. **Mobile gaming**: Works on phones and tablets
5. **Customize**: Modify the React client in `web_client/src/`

The dual system gives you the best of both worlds - the proven pygame desktop experience AND modern web multiplayer capabilities!

---

**Need the original pygame-only version?** Just run `python pyBomberMarv.py` - it's completely unchanged.