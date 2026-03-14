# Boss Battle Package for BallsDex 3.0

An improved and refactored Boss Battle package for BallsDex 3.0 with full admin panel integration.

## Credits

**Original Creator:** MoOfficial ([@moofficial on Discord](https://discord.com/users/moofficial))  
**Original Repository:** [MoOfficial0000/BossPackageBD](https://github.com/MoOfficial0000/BossPackageBD)  
**BallsDex 3.0 Conversion & Improvements:** Hayden

## Features

- **Admin Panel Integration**: Configure all boss settings from the Django admin panel
- **Dynamic Boss System**: Host boss battles with customizable HP, attack, and defense mechanics
- **Player Progression**: Track damage dealt, rounds survived, and overall performance
- **Flexible Reward System**: Choose between random winner, most damage, last hitter, or no winner
- **Custom Images**: Upload custom start/defend/attack images for each boss
- **Join Button UI**: Interactive button for players to join the battle
- **Comprehensive Logging**: All actions logged to configured channel
- **Admin Controls**: Manage boss state, disqualifications, and hackjoin players

## Installation

1. Clone or download this package into your BallsDex packages directory
2. Add `boss` to your `config.yml` under `packages`:

```yaml
packages:
  - ballsdex.packages.boss
```

3. Run migrations to create the database tables:

```bash
python manage.py makemigrations
python manage.py migrate
```

4. Create a Special called "Boss" in your admin panel:
   - Name: `Boss`
   - Rarity: `0`
   - End Date: Set to a far future date (e.g., 2124)
   - This special will be awarded to the winner

## Configuration

All configuration is done through the Django admin panel at `/admin/boss/`:

### Boss Settings
- **Shiny ATK Bonus**: Bonus attack for shiny balls (default: 1000)
- **Shiny HP Bonus**: Bonus HP for shiny balls (default: 1000)
- **Max ATK**: Maximum attack a card can have before buffs (default: 5000)
- **Max HP**: Maximum HP a card can have before buffs (default: 5000)
- **Min Boss Damage**: Minimum damage the boss deals in attack rounds (default: 0)
- **Max Boss Damage**: Maximum damage the boss deals in attack rounds (default: 2000)
- **Log Channel ID**: Discord channel ID for logging boss actions

## How to Play

### Admin Commands

1. **Start a Boss Battle**
   ```
   /boss admin start <countryball> <hp_amount> [start_image] [defend_image] [attack_image]
   ```
   - Choose a countryball (must have both collectible and wild cards)
   - Set HP amount
   - Optionally upload custom images

2. **Start a Round**
   ```
   /boss admin defend
   ```
   or
   ```
   /boss admin attack [attack_amount]
   ```
   - Defend: Boss defends, players deal damage
   - Attack: Boss attacks, players take damage (random or specified amount)

3. **End Current Round**
   ```
   /boss admin end_round
   ```
   - Displays player performance for the round
   - Removes dead players

4. **Conclude the Battle**
   ```
   /boss admin conclude <winner_type>
   ```
   - Random: Random survivor wins
   - Most Damage: Player with highest total damage wins
   - Last Hitter: Player who dealt the last hit wins
   - No Winner: Boss wins, no rewards

5. **Admin Tools**
   ```
   /boss admin hackjoin <user>
   ```
   - Manually add a player to the battle
   
   ```
   /boss admin disqualify <user>
   ```
   - Remove a player from the battle

### Player Commands

- **/boss join**: Join the current boss battle (also available via button)
- **/boss select**: Choose which ball to use for the current round
- **/boss stats**: View current boss stats and your performance

## Important Notes

1. **Countryball Requirements**: Boss balls must have BOTH collectible and wild cards. Balls created without wild cards will cause errors.

2. **Special Requirement**: You must create a "Boss" special in the admin panel before concluding battles.

3. **Image Files**: If no custom images are provided, the package will use the ball's default collection card.

4. **Round System**: 
   - Defend rounds: Players attack the boss
   - Attack rounds: Boss attacks players
   - Players must select a ball each round
   - Dead players are removed from the battle

5. **Stats Calculation**:
   - ATK/HP are capped at configured max values before shiny bonuses
   - Shiny balls receive configured bonus ATK/HP
   - Boss damage is either specified or randomized based on config

## Admin Panel Features

### Boss Settings
Manage global boss configuration including stat caps, shiny bonuses, damage ranges, and logging.

### Boss Battles
View active and past boss battles with full details on participants, rounds, and winners.

### Battle Participants
Track individual player performance across all boss battles.

### Disqualifications
Manage disqualified players and removal reasons.

## Support

For bugs or issues:
- Original package: Contact @moofficial on Discord
- BallsDex 3.0 conversion: Open an issue on the repository

## License

This package maintains the original license from MoOfficial's BossPackageBD repository.
