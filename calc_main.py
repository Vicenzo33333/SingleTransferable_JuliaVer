import pandas as pd
import tools as t
import google_sheet as gs
import classes as c


def start_calc(spreadsheet, question, seats):
	# input_tab: list[list[str]] = pd.read_excel(spreadsheet,input_tab)
	# ballots = pd.DataFrame(input_tab[1:], columns = input_tab[0])
	sheet = pd.read_excel(spreadsheet,sheet_name=0)
	#print(sheet)
	ballots = pd.DataFrame(sheet)
	#print(ballots)
	removable = []
	for column in ballots.columns:
		if question not in column:
			removable.append(column)
	#print(removable)
	ballots.drop(removable, axis = 1, inplace = True) #remove not question columns
	#print(ballots)
	columns = []
	for item in ballots.columns:
		item = item.replace(f"{question} [", "").replace("]", "") #clean strings to leave only names
		columns.append(item)

	ballots.columns = columns
	ballots = ballots.map(t.shorten) #changes to numbers
	print("finished applying map")
	# | | | | | Got Base Ballots | | | | |

	#Calculating averages and positions from each candidate
	averages = {}
	positions = {}
	for candidate in ballots.columns:
			ranks = ballots[candidate][ballots[candidate] > 0]
			if len(ranks) > 0:
				averages[candidate] = ranks.mean()
			else:
				averages[candidate] = 6767

			positions[candidate] = [len(ballots.columns)]
			for pos in range(1,  len(ballots.columns) + 1):
				positions[candidate].append((ballots[candidate] == pos).sum())
	print("finished calculating averages")




	vote = c.Vote(ballots, seats, averages, positions)

	response = "success"
	while response == "success":
		response = vote.add_tabulation_round()

	print("seats =" + str(seats))
	print(vote)
	gs.write_results2(vote,spreadsheet)
	#gs.write_results(spreadsheet, output_tab, vote)

