import configparser
import os
import time
import traceback
from tkinter import Tk
from tkinter import messagebox
import cv2 as cv
import numpy as np
import cProfile
import io
import pstats
import copy
import glob
import json

from range_key_dict import RangeKeyDict
import cassiopeia as cass
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from utils import utils
from train_model.model import ChampImgModel, ItemImgModel, SelfImgModel, NextItemModel, CSImgModel, \
    KDAImgModel, CurrentGoldImgModel, LvlImgModel, MultiTesseractModel
from utils.artifact_manager import ChampManager, ItemManager, SimpleManager
from utils.build_path import build_path
from constants import ui_constants, game_constants, app_constants
import functools
from train_model import data_loader
from collections import Counter

class NoMoreItemSlots(Exception):
    pass




class Main(FileSystemEventHandler):

    def __init__(self):
        # self.onTimeout = False
        # self.loldir = utils.get_lol_dir()
        # self.config = configparser.ConfigParser()
        # self.config.read(self.loldir + os.sep +"Config" + os.sep + "game.cfg")
        # try:
        # # res = 1440,810
        #     res = int(self.config['General']['Width']), int(self.config['General']['Height'])
        # except KeyError as e:
        #     print(repr(e))
        #     res = 1366, 768
        #     print("Couldn't find Width or Height sections")
        #
        # try:
        #     show_names_in_sb = bool(int(self.config['HUD']['ShowSummonerNamesInScoreboard']))
        # except KeyError as e:
        #     print(repr(e))
        #     show_names_in_sb = False
        #
        # try:
        #     flipped_sb = bool(int(self.config['HUD']['MirroredScoreboard']))
        # except KeyError as e:
        #     print(repr(e))
        #     flipped_sb = False
        #
        # try:
        #     hud_scale = float(self.config['HUD']['GlobalScale'])
        # except KeyError as e:
        #     print(repr(e))
        #     hud_scale = 0.5
        #
        #
        # if flipped_sb:
        #     Tk().withdraw()
        #     messagebox.showinfo("Error",
        #                         "League IQ does not work if the scoreboard is mirrored. Please untick the \"Mirror Scoreboard\" checkbox in the game settings (Press Esc while in-game)")
        #     raise Exception("League IQ does not work if the scoreboard is mirrored.")
        self.res_converter = ui_constants.ResConverter(1440,900, 0.48)
        # self.res_converter = ui_constants.ResConverter(*res, hud_scale=hud_scale, summ_names_displayed=show_names_in_sb)


       
        self.item_manager = ItemManager()
        # if Main.shouldTerminate():
        #     return
        with open(app_constants.train_paths["champ_vs_roles"], "r") as f:
            self.champ_vs_roles = json.load(f)
        self.early_or_late = "early"
        self.next_item_model_early = NextItemModel("early")
        self.next_item_model_early.load_model()
        self.next_item_model_late = NextItemModel("late")
        self.next_item_model_late.load_model()
        self.next_item_model = self.next_item_model_early

        # if Main.shouldTerminate():
        #     return
        self.champ_img_model = ChampImgModel(self.res_converter)
        self.champ_img_model.load_model()
        # if Main.shouldTerminate():
        #     return
        self.item_img_model = ItemImgModel(self.res_converter)
        self.item_img_model.load_model()
        # if Main.shouldTerminate():
        #     return
        self.self_img_model = SelfImgModel(self.res_converter)
        self.self_img_model.load_model()


        self.kda_img_model = KDAImgModel(self.res_converter)
        self.kda_img_model.load_model()
        self.tesseract_models = MultiTesseractModel([LvlImgModel(self.res_converter),
                                                     CSImgModel(self.res_converter),
                                                     CurrentGoldImgModel(self.res_converter)])

        self.previous_champs = None
        self.previous_kda = None
        self.previous_cs = None
        self.previous_lvl = None
        self.previous_self_index = None

        Main.test_connection()

    def set_res_converter(self, res_cvt):
        self.res_converter = res_cvt
        self.champ_img_model.res_converter = res_cvt
        self.item_img_model.res_converter = res_cvt
        self.self_img_model.res_converter = res_cvt
        self.kda_img_model.res_converter = res_cvt
        for model in self.tesseract_models.tesseractmodels:
            model.res_converter = res_cvt

    @staticmethod
    def test_connection(timeout=0):
        try:
            lol = build_path([], cass.Item(id=3040, region="KR"))
        except Exception as e:
            print(f"Connection error. Retry in {timeout}")
            time.sleep(timeout)
            Main.test_connection(5)


    @staticmethod
    def swap_teams(team_data):
        return np.concatenate([team_data[5:], team_data[:5]], axis=0)

    def summoner_items_slice(self, role):
        return np.s_[role * game_constants.MAX_ITEMS_PER_CHAMP:role * game_constants.MAX_ITEMS_PER_CHAMP + game_constants.MAX_ITEMS_PER_CHAMP]

    def all_items_counter2items_list(self, counter, lookup):
        items_id = [[], [], [], [], [], [], [], [], [], []]
        for i in range(10):
            items_id[i] = self.items_counter2items_list(counter[i], lookup)
        return items_id


    def items_counter2items_list(self, summ_items, lookup):
        result = []
        for item_key in summ_items:
            id_item = self.item_manager.lookup_by(lookup, item_key)
            result.extend([id_item] * summ_items[item_key])
        return result

    def predict_next_item(self, role, champs, items, cs, lvl, kda, current_gold):
        champs_int = [int(champ["int"]) for champ in champs]
        items_id = self.all_items_counter2items_list(items, "int")
        items_id = [[int(item["id"]) for item in summ_items] for summ_items in items_id]
        summ_owned_completes = None
        if self.early_or_late == "late":
            summ_owned_completes = list(self.item_manager.extract_completes(items[role]))
        return self.next_item_model.predict_easy(role, champs_int, items_id, cs, lvl, kda, current_gold,
                                                 summ_owned_completes)


    def build_path(self, items, next_item, current_gold):
        items = self.items_counter2items_list(items, "int")
        items_id = [int(item["main_img"]) if "main_img" in item else int(item["id"]) for item in items]
        
        #TODO: this is bad. the item class should know when to return main_img or id
        next_items, _, abs_items, _ = build_path(items_id, cass.Item(id=(int(next_item["main_img"]) if "main_img" in
                                                                                                       next_item else
                                                                         int(next_item["id"])), region="EUW"), current_gold)
        next_items = [self.item_manager.lookup_by("id", str(item_.id)) for item_ in next_items]
        abs_items = [[self.item_manager.lookup_by("id", str(item_)) for item_ in items_] for items_ in abs_items]
        return next_items, abs_items


    def remove_low_value_items(self, items):
        items = Counter(items)
        removable_items = ["Control Ward", "Health Potion", "Refillable Potion", "Corrupting Potion",
         "Cull", "Doran's Blade", "Doran's Shield", "Doran's Ring",
         "Rejuvenation Bead", "The Dark Seal", "Mejai's Soulstealer", "Faerie Charm"]
        removal_index = 0
        delta_items = Counter()
        six_items = None
        delta_six = None


        while NextItemModel.num_itemslots(items) >= game_constants.MAX_ITEMS_PER_CHAMP:
            if NextItemModel.num_itemslots(items) == game_constants.MAX_ITEMS_PER_CHAMP:
                six_items = Counter(items)
                delta_six = Counter(delta_items)
            if removal_index >= len(removable_items):
                break
            item_to_remove = self.item_manager.lookup_by("name", removable_items[removal_index])['int']
            if item_to_remove in items:
                delta_items += Counter({item_to_remove: items[item_to_remove]})
            items -= delta_items
            removal_index += 1

        return items, delta_items, six_items, delta_six

    def simulate_game(self, items, champs):
        count = 0
        at_same_number = 0
        last_number = 0
        while count != 10:
            count = 0
            for summ_index in range(10):
                if summ_index == 5:

                    champs, items = self.swap_teams(champs, items)
                count += int(self.next_item_for_champ(summ_index % 5, champs, items))

            if count == last_number:
                at_same_number += 1
                if count > 6 and at_same_number >= 10:
                    break
            else:
                at_same_number = 0
                last_number = count
            champs, items = self.swap_teams(champs, items)
            for i, item in enumerate(items):
                print(f"{divmod(i, 6)}: {item}")
            pass


    def analyze_champ(self, role, champs, items, cs, lvl, kda, current_gold):
        cg_max_wait_gold = 30
        current_gold += cg_max_wait_gold
        assert (len(champs) == 10)
        print("\nRole: " + str(role))

        if role > 4:
            print("Switching teams!")
            champs = self.swap_teams(champs)
            items = self.swap_teams(items)
            lvl = self.swap_teams(lvl)
            cs = self.swap_teams(cs)
            kda = self.swap_teams(kda)
            role -= 5

        result = []

        thresholds = [0, 0.05, 0.1, 0.25, 1.0]
        num_full_items = [0, 1, 2, 3]
        commonality_to_items = dict()
        for i in range(len(num_full_items)):
            commonality_to_items[(thresholds[i], thresholds[i+1])] = num_full_items[i]
        commonality_to_items = RangeKeyDict(commonality_to_items)

        while current_gold > 0:

            num_true_completes_owned = len(list(self.item_manager.extract_completes(items[role], True)))
            # start_buy = sum(items[role].values()) < 3 and self.recipe_cost([self.item_manager.lookup_by("int",
            #                                                                                       item_int) for
            #                                                item_int in items[role]]) < 500
            champ_vs_role_commonality = self.champ_vs_roles[str(champs[role]["int"])].get(game_constants.ROLE_ORDER[role], 0)
            print(f"champ vs roles commonality: {champ_vs_role_commonality}")
            allowed_items = commonality_to_items[champ_vs_role_commonality]


            if num_true_completes_owned < allowed_items:
                self.early_or_late = "early"
                self.next_item_model = self.next_item_model_early
                print("USING early GAME MODEL")
            else:
                self.early_or_late = "late"
                self.next_item_model = self.next_item_model_late
                print("USING late GAME MODEL")

            if NextItemModel.num_itemslots(items[role]) >= game_constants.MAX_ITEMS_PER_CHAMP:

                items_five, delta_five, items_six, delta_six = self.remove_low_value_items(items[role])
                # items[role], delta_items = self.remove_low_value_items(items[role])

                for items_reduction, deltas in zip([items_six, items_five],[delta_six, delta_five]):
                    if items_reduction is None:
                        continue
                    copied_items = [Counter(summ_items) for summ_items in items]
                    copied_items[role] = items_reduction
                    delta_items = deltas
                    try:
                        next_predicted_items = self.predict_next_item(role, champs, copied_items, cs, lvl, kda, current_gold)
                        next_item = next_predicted_items[0]
                    except ValueError as e:
                        print(e)
                        print("max items reached. thats it")
                        return result

                    if next_item["name"] == "Empty":
                        continue
                    next_items, abs_items = self.build_path(copied_items[role], next_item, current_gold)
                    updated_items = Counter([item["int"]  for item in abs_items[-1]])
                    if NextItemModel.num_itemslots(updated_items) <= game_constants.MAX_ITEMS_PER_CHAMP:
                        break
            else:
                delta_items = None
                try:
                    next_predicted_items = self.predict_next_item(role, champs, items, cs, lvl, kda, current_gold)
                    next_item = next_predicted_items[0]
                except ValueError as e:
                    print(e)
                    print("max items reached. thats it")
                    return result

                if next_item["name"] == "Empty":
                    return self.return_result(next_predicted_items, result)

                next_items, abs_items = self.build_path(items[role], next_item, current_gold)
                updated_items = Counter([item["int"] for item in abs_items[-1]])

            if next_item["name"] == "Empty":
                return self.return_result(next_predicted_items, result)

            for ni in next_items:
                cass_item_cost = cass.Item(id=(int(ni["main_img"]) if "main_img" in
                                                             ni else int(ni["id"])),
                           region="KR").gold.base
                current_gold -= cass_item_cost
                if current_gold < -50:
                    return self.return_result(next_predicted_items, result)
                else:
                    result.append(ni)



            items[role] = updated_items
            current_summ_items = [self.item_manager.lookup_by("int", item) for item in items[role]]
            if delta_items:
                for delta_item in delta_items:
                    if delta_item in items[role]:
                        items[role][delta_item] = items[role][delta_item] - delta_items[delta_item]
                    else:
                        items[role] += Counter({delta_item:delta_items[delta_item]})

                delta_items = None
            items[role] = +items[role]
        return result


    def return_result(self, next_items, result):
        if not result:
            for next_item in next_items:
                if next_item["name"] != "Empty":
                    return [next_item]
        return result


    def deflate_items(self, items):
        items_counter = Counter([item["id"] for item in items])
        large_item_sub_comps = Counter()
        for item in items:
            item = cass.Item(id=(int(item["id"])), region="EUW")
            comps = Counter([ str(item_comp.id) for item_comp in list(item.builds_from)])
            if comps:
                large_item_sub_comps += Counter(comps)
        return self.items_counter2items_list(items_counter - large_item_sub_comps, "id")



    def recipe_cost(self, next_items):
        return sum([cass.Item(id=(int(next_item["main_img"]) if "main_img" in
                                                                         next_item else int(next_item["id"])),
                                       region="KR").gold.base for next_item in next_items])

    def on_created(self, event):
        # pr.enable()
        
        # prevent keyboard mashing
        if self.onTimeout:
            return
        file_path = event.src_path
        print("Got event for file %s" % file_path)
        # stupid busy waiting until file finishes writing
        oldsize = -1
        while True:
            size = os.path.getsize(file_path)
            if size == oldsize:
                break
            else:
                oldsize = size
                time.sleep(0.05)

        self.process_image(event.src_path)
        
        # pr.disable()
        # s = io.StringIO()
        # sortby = 'cumulative'
        # ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        # ps.print_stats()
        # print(s.getvalue())

        self.timeout()

    def run_test_games(self):
        with open('test_data/items_test/setups.json', "r") as f:
            games = json.load(f)
        for key in games:
            champs = games[key]["champs"]
            items = games[key]["items"]

            champs = [ChampManager().lookup_by('name', champ) for champ in champs]
            items = [ItemManager().lookup_by('name', item) for item in items]
            items = np.delete(items, np.arange(6, len(items), 7))
            print(f"----------- SIMULATING {key}--------------------------")
            print(champs)
            print(items)
            self.simulate_game(items, champs)



    def timeout(self):
        self.onTimeout = True
        time.sleep(5.0)
        self.onTimeout = False

    def repair_failed_predictions(self, predictions, lower, upper):
        assert(len(predictions) == 10)
        for i in range(len(predictions)):
            #this pred is wrong
            if upper < predictions[i] or predictions[i] < lower:
                opp_index = (i + 5) % 10
                opp_pred_valid = predictions[opp_index] > lower and predictions[opp_index] < upper
                if opp_pred_valid:
                    predictions[i] = predictions[opp_index]
                else:
                    predictions[i] = sum(predictions)/10
        return predictions

    def process_image(self, img_path):

        print('you pressed tab + f12 ' + img_path)

        try:
            print("Now trying to predict image")
            screenshot = cv.imread(img_path)
            # utils.show_coords(screenshot, self.champ_img_model.coords, self.champ_img_model.img_size)
            print("Trying to predict champ imgs")
            
            champs = list(self.champ_img_model.predict(screenshot))
            print(f"Champs: {champs}\n")

            try:
                kda = list(self.kda_img_model.predict(screenshot))
            except Exception as e:
                kda = [[0,0,0]]*10
            print(f"KDA:\n {kda}\n")
            kda = np.array(kda)
            kda[:, 0] = self.repair_failed_predictions(kda[:, 0], 0, 25)
            kda[:, 1] = self.repair_failed_predictions(kda[:, 1], 0, 25)
            kda[:, 2] = self.repair_failed_predictions(kda[:, 2], 0, 25)
            tesseract_result = self.tesseract_models.predict(screenshot)
            try:
                lvl = next(tesseract_result)
            except Exception as e:
                print(e)
                lvl = [0]*10
            lvl = self.repair_failed_predictions(lvl, 1, 18)

            try:
                cs = next(tesseract_result)
            except Exception as e:
                print(e)
                cs = [0]*10
            cs = self.repair_failed_predictions(cs, 0, 400)
            try:
                current_gold = next(tesseract_result)[0]
            except Exception as e:
                print(e)
                current_gold = 500

            if current_gold > 4000:
                current_gold = 4000
            elif current_gold < 0 or not current_gold:
                current_gold = 500
            
            print(f"Lvl:\n {lvl}\n")
            print(f"CS:\n {cs}\n")
            print(f"Current Gold:\n {current_gold}\n")
            print("Trying to predict item imgs. \nHere are the raw items: ")
            items = list(self.item_img_model.predict(screenshot))
            # for i, item in enumerate(items):
            #     print(f"{divmod(i, 7)}: {item}")
            items = [self.item_manager.lookup_by("int", item["int"])  for item in items]
            print("Here are the converted items:")
            for i, item in enumerate(items):
                print(f"{divmod(i, 7)}: {item}")
            print("Trying to predict self imgs")
            self_index = self.self_img_model.predict(screenshot)
            print(self_index)

            def prev_champs2champs(prev_champs):
                repaired_champs_int = [max(pos_counter, key=lambda k: pos_counter[k]) for pos_counter in
                                       prev_champs]
                return [ChampManager().lookup_by("int", champ_int) for champ_int in repaired_champs_int]


            champs_int = [champ["int"] for champ in champs]

            #sometimes we get incorrect champ img predictions. we need to detect this and correct for it by taking
            # the previous prediction
            if not self.previous_champs:
                self.previous_champs = [Counter({champ_int: 1}) for champ_int in champs_int]
                self.previous_kda = kda
                self.previous_cs = cs
                self.previous_lvl = lvl
                self.previous_self_index = self_index

            else:
                champ_overlap = np.sum(np.equal(champs, prev_champs2champs(self.previous_champs)))
                #only look at top 3 kdas since the lower ones often are overlapped
                k_increase = np.all(np.greater_equal(kda[:3,0], self.previous_kda[:3,0]))
                d_increase = np.all(np.greater_equal(kda[:3, 1], self.previous_kda[:3, 1]))
                a_increase = np.all(np.greater_equal(kda[:3, 2], self.previous_kda[:3, 2]))
                # cs_increase = np.all(np.greater_equal(cs, self.previous_cs))
                # lvl_increase = np.all(np.greater_equal(cs, self.previous_cs))
                # all_increased = k_increase and d_increase and a_increase and cs_increase and lvl_increase

                #this is still the same game
                if champ_overlap > 7 and k_increase and d_increase and a_increase:
                    print("SAME GAME. taking previous champs")
                    champs = prev_champs2champs(self.previous_champs)
                    self.previous_champs = [prev_champs_counter + Counter({champ_int: 1}) for
                                            champ_int, prev_champs_counter
                                            in zip(champs_int, self.previous_champs)]
                #this is a new game
                else:
                    self.previous_champs = [Counter({champ_int: 1}) for champ_int in champs_int]
                self.previous_kda = kda
                self.previous_cs = cs
                self.previous_lvl = lvl
                self.previous_self_index = self_index


        except FileNotFoundError as e:
            print(e)
            return
        except Exception as e:
            print(e)
            traceback.print_exc()
            return

        #remove items that the network is not trained on, such as control wards
        items = [item if (item["name"] != "Warding Totem (Trinket)" and item[
            "name"] != "Farsight Alteration" and item["name"] != "Oracle Lens") else self.item_manager.lookup_by("int", 0) for item in
                 items]

        #we don't care about the trinkets
        items = np.delete(items, np.arange(6, len(items), 7))

        items = np.array([summ_items["int"] for summ_items in items])
        items = np.reshape(items, (game_constants.CHAMPS_PER_GAME, game_constants.MAX_ITEMS_PER_CHAMP))
        items = [Counter(summ_items) for summ_items in items]
        for summ_items in items:
            del summ_items[0]

        #
        # items = [self.item_manager.lookup_by('int', 0)] * 60
        # items[30:] = [self.item_manager.lookup_by('int', 0)]*30
        # champs[0] = ChampManager().lookup_by('name', 'Aatrox')
        # champs[2] = ChampManager().lookup_by('name', 'Vladimir')
        # champs[4] = ChampManager().lookup_by('name', 'Soraka')


        # x = np.load(sorted(glob.glob(app_constants.train_paths[
        #                                  "next_items_early_processed"] + 'train_x*.npz'))[0])['arr_0']
        #
        # y = np.load(sorted(glob.glob(app_constants.train_paths[
        #                                  "next_items_early_processed"] + 'train_y*.npz'))[0])['arr_0']
        #
        # items = [ItemManager().lookup_by("int", item) for item in x[25][10:]]
        # champs = [ChampManager().lookup_by("int", champ) for champ in x[0][:10]]
        # self.simulate_game(items, champs)

        # for summ_index in range(10):
        #     champs_copy = copy.deepcopy(champs)
        #     items_copy = copy.deepcopy(items)
        #     items_to_buy = self.analyze_champ(summ_index, champs_copy, items_copy)
        #     print(f"This is the result for summ_index {summ_index}: ")
        #     print(items_to_buy)



        items_to_buy = self.analyze_champ(self_index, champs, items, cs, lvl, kda, current_gold)
        items_to_buy = self.deflate_items(items_to_buy)
        print(f"This is the result for summ_index {self_index}: ")
        print(items_to_buy)
        out_string = ""
        if items_to_buy and items_to_buy[0]:
            out_string += str(items_to_buy[0]["id"])
        for item in items_to_buy[1:]:
            out_string += "," + str(item["id"])
        # with open(os.path.join(os.getenv('LOCALAPPDATA'), "League IQ", "last"), "w") as f:
        #     f.write(out_string)

    @staticmethod
    def shouldTerminate():
        return os.path.isfile(os.path.join(os.getenv('LOCALAPPDATA'), "League IQ", "terminate"))

    def run(self):
        
        observer = Observer()
        ss_path = os.path.join(self.loldir, "Screenshots")
        print(f"Now listening for screenshots at: {ss_path}")
        observer.schedule(self, path=ss_path)
        observer.start()
        try:
            with open(os.path.join(os.getenv('LOCALAPPDATA'), "League IQ", "ai_loaded"), 'w') as f:
                f.write("true")
            while not Main.shouldTerminate():
                time.sleep(1)
            observer.stop()
            os.remove(os.path.join(os.getenv('LOCALAPPDATA'), "League IQ", "terminate"))
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

m = Main()
#m.run()

# m.process_image(f"Screen516.png")
for i in range(13,40):
    m.process_image(f"Screen5{i}.png")

# m.run_test_games()

# pr = cProfile.Profile()

# dataloader_1 = data_loader.UnsortedNextItemsDataLoader()
# X_un = dataloader_1.get_train_data()
# dataloader = data_loader.SortedNextItemsDataLoader(app_constants.train_paths["next_items_processed_sorted_inf"])
# X, Y = dataloader.get_train_data()
# m = NextItemEarlyGameModel()
# X = X[Y==2]
# X_ = X[:, 1:]
# X_ = X_[500:700]
# m.output_logs(X[:200].astype(np.float32))

#
# blob = cv.imread("blob.png", cv.IMREAD_GRAYSCALE )
# cv.imshow("blob", blob)
# cv.waitKey(0)
# ret, thresholded = cv.threshold(blob, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
# cv.imshow("thresholded", thresholded)
# cv.waitKey(0)
#
# from train_model.model import CurrentGoldImgModel, CSImgModel, LvlImgModel, MultiTesseractModel
# with open('test_data/easy/test_labels.json', "r") as f:
#     elems = json.load(f)

# base_path = "test_data/easy/"
# m = Main()


# for key in elems:


#     if elems[key]["hud_scale"] != None:
#         test_image_y = elems[key]

#         m.set_res_converter(ui_constants.ResConverter(*(test_image_y["res"].split(",")), elems[key]["hud_scale"],
#                                                       elems[key]["summ_names_displayed"]))

#         m.process_image(base_path + test_image_y["filename"])

            # KDAImgModel(res_cvt).predict(test_image_x)

# cass.Item(id=2055, region="KR")