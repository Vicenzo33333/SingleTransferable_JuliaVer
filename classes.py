import pandas as pd
from numpy import nan
import tools as t
from math import floor


class RandLog:
	def __init__(self, pool, chosen, random_for):
		self.pool = pool
		self.chosen = chosen
		self.random_for: str = random_for


class Vote:
	def __init__(self, ballots: pd.DataFrame, seats, averages, positions):
		self.seats = seats
		self._original_expired: int = 0
		self.averages = averages
		self.positions = positions

		# init-ing weight and support columns
		for column in ballots.columns:
			if ballots[column][0] is None:
				ballots[column] = [nan] * len(ballots[column])

		ballots, self._original_expired = t.delete_expired(ballots)
		ballots = t.recalc_support(ballots)
		ballots["Weight"] = [1] * len(ballots["Supports"])

		self._original_ballots: pd.DataFrame = t.deepcopy(ballots)
		self.quota = floor(len(ballots)) / self.seats
		self.tabulation_rounds: list[TabulationRound] = []

	def get_original_ballots(self) -> pd.DataFrame:
		return t.deepcopy(self._original_ballots)

	def get_original_expired(self) -> int:
		return t.deepcopy(self._original_expired)

	def get_all_candidates(self) -> list[str]:
		return self._original_ballots.columns[:-2]

	def get_all_elected(self) -> list[str]:
		elected = []
		for tabulation_round in self.tabulation_rounds:
			elected = elected + tabulation_round.elected
		return elected

	def get_all_eliminated(self) -> list[str]:
		eliminated = []
		for tabulation_round in self.tabulation_rounds:
			eliminated = eliminated + tabulation_round.eliminated
		return eliminated

	def get_all_random_logs(self) -> list[list[RandLog]]:
		rand_log_list = []
		for tabulation_round in self.tabulation_rounds:
			rand_log_list.append(tabulation_round.random_log)
		return rand_log_list

	def get_election_votes(self, elected: str) -> int:
		for tabulation_round in self.tabulation_rounds:
			if elected in tabulation_round.elected:
				return tabulation_round.get_starting_vote_count()[elected]

	def add_tabulation_round(self) -> str:
		if len(self.get_all_elected()) < self.seats and len(self.get_all_elected()) + len(self.get_all_eliminated()) != len(self.get_all_candidates()):
			if self.tabulation_rounds:
				new_round = TabulationRound(t.deepcopy(self.tabulation_rounds[-1].outgoing_ballots), self)
			else:
				new_round = TabulationRound(t.deepcopy(self._original_ballots), self)

			self.tabulation_rounds.append(new_round)
			return "success"
		else:
			return "full"


class TabulationRound:
	def __init__(self, ballots, parent_vote):
		self.parent_vote: Vote = parent_vote
		self.random_log: list[RandLog] = []
		self.expired: int = 0

		self._starting_ballots: pd.DataFrame = t.deepcopy(ballots)
		self._starting_vote_count: dict[str: int] = t.get_vote_count(self._starting_ballots)

		self.elected: list[str] = []
		self.eliminated: list[str] = []

		self.outgoing_ballots: pd.DataFrame = None
		self.outgoing_vote_count: dict[str: int] = None

		if len(self.get_starting_ballots().columns[:-2]) == self.parent_vote.seats - len(self.parent_vote.get_all_elected()):
			for person in self.get_starting_ballots().columns[:-2]:
				self.elected.append(person)
		else:
			for person in self._starting_vote_count.keys():
				vote = self._starting_vote_count[person]
				if vote >= self.parent_vote.quota:
					self.election_round()
					break
			else:
				self.elimination_round()

	def get_starting_ballots(self) -> pd.DataFrame:
		return t.deepcopy(self._starting_ballots)

	def get_starting_vote_count(self) -> dict[str: int]:
		return t.deepcopy(self._starting_vote_count)

	def get_all_starting_candidates(self):
		return self._starting_vote_count.keys()

	def election_round(self):
		sorted_candidates = pd.Series(data=self._starting_vote_count).sort_values(ascending=False).keys()
		winner = sorted_candidates[0]

		# We check if the person with the most votes is tied with someone else. If they are, we pick best avg, most 1st choice, etc to distribute before
		most_votes = [candidate for candidate in sorted_candidates if self._starting_vote_count[candidate] == self._starting_vote_count[winner]]
		if len(most_votes) > 1:
			tied_candidates = [candidate for candidate in sorted_candidates if self.parent_vote.averages[candidate] == self.parent_vote.averages[winner]]
			min_avg = min(self.parent_vote.averages[candidate] for candidate in tied_candidates)
			tied_candidates = [candidate for candidate in tied_candidates if self.parent_vote.averages[candidate] == min_avg]
			if len(tied_candidates) > 1:
				# Most 1st choice votes, 2nd, etc
				len_pos = len(self.parent_vote.positions[tied_candidates[0]])
				for post in range(len_pos):
					max_vote = max(self.parent_vote.positions[candidate] for candidate in tied_candidates)
					people = [candidate for candidate in tied_candidates if self.parent_vote.positions[candidate] == max_vote]
					if len(people) == 1:
						break
			winner = tied_candidates[0]

		max_votes = max(self._starting_vote_count.values())
		self.random_log.append(RandLog([winner], winner, "elect"))
		self.elected.append(winner)

		# make surplus adjustments
		if self.outgoing_ballots is None:
			self.outgoing_ballots = self.get_starting_ballots()

		if self._starting_vote_count[winner] > self.parent_vote.quota:
			self.surplus_calc(winner)
		else:
			self.outgoing_ballots.drop([winner], axis = 1, inplace = True)
			self.outgoing_ballots, deleted = t.remove_electee_ballots(self.outgoing_ballots, winner)
			self.expired += deleted


		# recalc vote_count after all is done
		self.outgoing_ballots, deleted = t.delete_expired(self.outgoing_ballots)
		self.expired += deleted
		self.outgoing_ballots = t.recalc_support(self.outgoing_ballots)
		self.outgoing_vote_count: dict[str: int] = t.get_vote_count(self.outgoing_ballots)

	def elimination_round(self):
		# get the lowest vote
		first = True
		lowest = None
		for person in self._starting_vote_count.keys():
			if first:
				lowest = self._starting_vote_count[person]
				first = False
			else:
				if self._starting_vote_count[person] < lowest:
					lowest = self._starting_vote_count[person]

		# get people with the lowest vote
		people = []
		for person in self._starting_ballots.columns[:-2]:
			if self._starting_vote_count[person] == lowest:
				people.append(person)

		# eliminate
		if len(people) > 1:
			#Worst average
			max_avg = max(self.parent_vote.averages[candidate] for candidate in people)
			people = [candidate for candidate in people if self.parent_vote.averages[candidate] == max_avg]
			if len(people) > 1:
				#Less 1st choice votes, 2nd, etc
				len_pos = len(self.parent_vote.positions[people[0]])
				for post in range(len_pos):
					min_vote = min(self.parent_vote.positions[candidate] for candidate in people)
					people = [candidate for candidate in people if self.parent_vote.positions[candidate] == min_vote]
					if len(people) == 1:
						break

		eliminated = people[-1]
		self.random_log.append(RandLog(people, eliminated, "eliminated"))
		self.eliminated.append(eliminated)

		# Calculate value per transferred ballot to transfer
		loser_ballots = self._starting_ballots[self._starting_ballots["Supports"] == eliminated]
		inherited_ballots = loser_ballots[loser_ballots["Weight"] < 1]
		total_quota = inherited_ballots["Weight"].sum()

		adjusted_ballots = self._starting_ballots.drop([eliminated], axis = 1, inplace = False)

		adjusted_ballots, deleted = t.delete_expired(adjusted_ballots)
		self.expired += deleted

		loser_ballots = adjusted_ballots[adjusted_ballots["Supports"] == eliminated]
		inherited_ballots = loser_ballots[loser_ballots["Weight"] < 1]

		if not inherited_ballots.empty:
			value_per_ballot = total_quota / len(inherited_ballots)
		else:
			value_per_ballot = 0

		# adjust ballots
		new_weights = []
		for i, line in adjusted_ballots.iterrows():
			if line["Supports"] == eliminated and line["Weight"] != 1:
				new_weights.append(value_per_ballot)
			else:
				new_weights.append(line["Weight"])
		adjusted_ballots["Weight"] = new_weights

		# save outcome
		self.outgoing_ballots = adjusted_ballots
		self.outgoing_ballots = t.recalc_support(self.outgoing_ballots)
		self.outgoing_vote_count = t.get_vote_count(self.outgoing_ballots)

	def surplus_calc(self, winner):
		adjusted_ballots = t.deepcopy(self.outgoing_ballots)

		# drop person
		adjusted_ballots.drop([winner], axis = 1, inplace = True)
		adjusted_ballots, deleted = t.delete_expired(adjusted_ballots)
		self.expired += deleted

		winner_ballots = adjusted_ballots[adjusted_ballots["Supports"] == winner]
		if not winner_ballots.empty:
			value_per_ballot = (self._starting_vote_count[winner] - self.parent_vote.quota) / len(winner_ballots)
		else:
			value_per_ballot = 0

		# adjust ballots
		new_weights = []
		for i, line in adjusted_ballots.iterrows():
			if line["Supports"] == winner:
				new_weights.append(value_per_ballot)
			else:
				new_weights.append(line["Weight"])
		adjusted_ballots["Weight"] = new_weights

		adjusted_ballots = t.recalc_support(adjusted_ballots)

		# save outcome
		self.outgoing_ballots = adjusted_ballots
		self.outgoing_vote_count: dict[str: int] = t.get_vote_count(self.outgoing_ballots)

	def get_last_ballots(self):
		if self.outgoing_ballots is not None:
			return t.deepcopy(self.outgoing_ballots)
		else:
			return t.deepcopy(self.get_starting_ballots())

	def get_last_votes(self):
		if self.outgoing_vote_count is not None:
			return t.deepcopy(self.outgoing_vote_count)
		else:
			return t.deepcopy(self.get_starting_vote_count())


