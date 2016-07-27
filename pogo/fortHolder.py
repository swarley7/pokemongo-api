#!/usr/bin/python
import argparse
import logging
import time
import sys
import traceback

from custom_exceptions import GeneralPogoException

from api import PokeAuthSession
from location import Location

from pokedex import pokedex
from inventory import items


def setupLogger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)


def displayProfile(session):
    s = ""
    s += session.getProfile().player_data.username
    s += " Level:"
    inv = session.getInventory()
    stats = inv.stats
    s += str(stats.level)
    s += " XP to next: "
    s += str(stats.next_level_xp - stats.experience)
    s += " Pokedex: "
    s += str(stats.unique_pokedex_entries)+"/151"
    s += " Party size: "
    s += str(len(inv.party))
    s += " Strongest: "
    if len(inv.party) > 0:
        s += str(getStrongestPokeInPartyString(inv.party))
    else:
        s += "NA"
    logging.info("(PROFILE)\t-\t"+s)

def getStrongestPokeInParty(party):
    strongest = 0
    ret = 0
    for poke in party:
        if poke.cp > strongest:
            strongest = poke.cp
            ret = poke
    return ret

def getStrongestPokeInPartyString(party):
    poke = getStrongestPokeInParty(party)
    return str(pokedex[poke.pokemon_id]) + " " + str(poke.cp) +" CP"

def sortCloseForts(session):
    # Sort nearest forts (pokestop)
    cells = session.getMapObjects()
    latitude, longitude, _ = session.getCoordinates()
    ordered_forts = []
    for cell in cells.map_cells:
        for fort in cell.forts:
            dist = Location.getDistance(
                latitude,
                longitude,
                fort.latitude,
                fort.longitude
            )
            if fort.type == 0:
                ordered_forts.append({'distance': dist, 'fort': fort})

    ordered_forts = sorted(ordered_forts, key=lambda k: k['distance'])
    return [instance['fort'] for instance in ordered_forts]

def getClosestUnheldFort(session):
    return sortCloseForts(session)[0]

def getStrongest6PokeInParty(session):
    pokes = orderPokes(session)  # ascending
    pokes = pokes[::-1]  # descending
    r = []
    for i in range(6):
        r.append(pokes[i])
    return r

def orderPokes(session):
    pokes = session.getInventory().party
    ordered_forts = []
    for poke in pokes:
        cp = poke.cp
        ordered_forts.append({'cp': cp, 'poke': poke})
    ordered_forts = sorted(ordered_forts, key=lambda k: k['cp'])
    return [instance['poke'] for instance in ordered_forts]

def beginBattle(session, fort):
    # gym_id (str)
    gym_id = fort.id
    # attacking_pokemon_ids (list)
    attackers = getStrongest6PokeInParty(session) # or use your own function to pick
    attacking_pokemon_ids = []
    for poke in attackers:
        attacking_pokemon_ids.append(poke.id)
    # defending_pokemon_id (??) let's try the lowest value at the gym
    defending_pokemon_id = session.getGymDetails(fort).gym_state.memberships[0].pokemon_data.id
    # alternatively: defending_pokemon_id = get_defending_pokemon(session, fort)
    # lat
    # lon
    lat, lon, _ = session.getCoordinates()
    print "OK"
    print "BATTLEID", session.getBattleId(gym_id, attacking_pokemon_ids, defending_pokemon_id, lat, lon)
    print "DUN"
    return "dongs"

def fightGym(session, fort):
    # required to send attack msg:
    # get gym id (str)
    gym_id = fort.id
    # get battle id (str)
    battle_id = beginBattle(session,fort)
    # get attack actions (list)
    # last_retrieved_action
    # player lat
    # player lon
    return "dongs"

def holdFort(fort):
    # walk to fort
    #
    print fightGym(session, fort)
    return "dongs"

# fortbot
def fortBot(session):
    cooldown = 10
    if True:#while True:
        try:
            fort = getClosestUnheldFort(session)
            holdFort(fort)
        # Catch problems and reauthenticate
        except GeneralPogoException as e:
            logging.critical('GeneralPogoException raised: %s', e)
            session = poko_session.reauthenticate(session)
            time.sleep(cooldown)

        except Exception as e:
            logging.critical('Exception raised: %s', e)
            traceback.print_exc()
            session = poko_session.reauthenticate(session)
            time.sleep(cooldown)

# Entry point
# Start off authentication and demo
if __name__ == '__main__':
    setupLogger()
    logging.debug('Logger set up')

    # Read in args
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--auth", help="Auth Service", required=True)
    parser.add_argument("-u", "--username", help="Username", required=True)
    parser.add_argument("-p", "--password", help="Password", required=True)
    parser.add_argument("-l", "--location", help="Location")
    parser.add_argument("-g", "--geo_key", help="GEO API Secret")
    args = parser.parse_args()

    # Check service
    if args.auth not in ['ptc', 'google']:
        logging.error('Invalid auth service {}'.format(args.auth))
        sys.exit(-1)

    # Create PokoAuthObject
    poko_session = PokeAuthSession(
        args.username,
        args.password,
        args.auth,
        geo_key=args.geo_key
    )

    # Authenticate with a given location
    # Location is not inherent in authentication
    # But is important to session
    if args.location:
        session = poko_session.authenticate(locationLookup=args.location)
    else:
        session = poko_session.authenticate()

    # Time to show off what we can do
    if session:
        fortBot(session)
        # General
#        getProfile(session)
#        getInventory(session)

        # Pokemon related
#        pokemon = findBestPokemon(session)
#        walkAndCatch(session, pokemon)

        # Pokestop related
#        fort = findClosestFort(session)
#        walkAndSpin(session, fort)

        # see simpleBot() for logical usecases
        # eg. simpleBot(session)

    else:
        logging.critical('Session not created successfully')
