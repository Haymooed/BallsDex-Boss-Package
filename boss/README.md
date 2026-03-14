# Boss Battle Package

Boss Battle system for BallsDex 3.0 with full database integration and admin panel support.

## Original Creator
**MoOfficial** ([@moofficial on Discord](https://discord.com/users/moofficial))

## BallsDex 3.0 Conversion
**Hayden**

## Installation

1. Copy the `boss` folder to your BallsDex packages directory
2. Add to `config.yml`:
```yaml
packages:
  - ballsdex.packages.boss
```

3. Run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

4. Create a "Boss" special in your admin panel:
   - Name: Boss
   - Rarity: 0
   - End date: 2124 (far future)

## Admin Panel Configuration

Access `/admin/boss/` to configure:

- **Boss Settings**: Shiny bonuses, stat caps, damage ranges, log channel
- **Boss Battles**: View all battles (active and past)
- **Battle Participants**: Track player performance
- **Round Actions**: Detailed round-by-round actions
- **Disqualified Players**: Manage disqualifications

## Commands

### Admin Commands (`/boss admin`)

- `start` - Start a new boss battle
- `defend` - Start a defend round (players attack boss)
- `attack` - Start an attack round (boss attacks players)
- `end_round` - End current round and show results
- `conclude` - End battle and award winner
- `hackjoin` - Manually add a player
- `disqualify` - Disqualify/undisqualify a player

### Player Commands (`/boss`)

- `select` - Choose your ball for the current round
- `stats` - View your current stats

## Features

✅ Database-backed (no data loss on restart)
✅ Admin panel integration
✅ Customizable settings
✅ Shiny ball bonuses
✅ Detailed stat tracking
✅ Discord logging
✅ Interactive join button
✅ Multiple winner modes (Random, Most Damage, Last Hitter, No Winner)
