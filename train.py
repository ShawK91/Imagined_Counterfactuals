from core.agent import Agent, TestAgent
from core.mod_utils import pprint, str2bool
import numpy as np, os, time, torch
from core import mod_utils as utils
from core.runner import rollout_worker
from torch.multiprocessing import Process, Pipe
import core.mod_utils as mod
import argparse
import random
import threading, sys

parser = argparse.ArgumentParser()
parser.add_argument('-popsize', type=int, help='#Evo Population size', default=10)
parser.add_argument('-rollsize', type=int, help='#Rollout size for agents', default=50)
parser.add_argument('-env', type=str, help='Env to test on?', default='rover_heterogeneous')
parser.add_argument('-config', type=str, help='World Setting?', default='fire_truck_uav_long_range_lidar') # todo: change this for different coupling requirements
parser.add_argument('-matd3', type=str2bool, help='Use_MATD3?', default=False)
parser.add_argument('-maddpg', type=str2bool, help='Use_MADDPG?', default=False)
parser.add_argument('-reward', type=str, help='Reward Structure? 1. mixed 2. global', default='global')
parser.add_argument('-frames', type=float, help='Frames in millions?', default=20)
parser.add_argument('-dpp', type=str2bool, help='Use DPP?', default=False)
parser.add_argument('-action_space', type=str, help='different or same?', default='same') # todo: for different speeds of each agents

parser.add_argument('-filter_c', type=int, help='Prob multiplier for evo experiences absorbtion into buffer?', default=1)
parser.add_argument('-evals', type=int, help='#Evals to compute a fitness', default=1)
parser.add_argument('-seed', type=int, help='#Seed', default=2018)
parser.add_argument('-algo', type=str, help='SAC Vs. TD3?', default='TD3')
parser.add_argument('-savetag', help='Saved tag', default='')
parser.add_argument('-gradperstep', type=float, help='gradient steps per frame', default=0.1)
parser.add_argument('-pr', type=float, help='Prioritization?', default=0.0)
#parser.add_argument('-use_gpu', type=str2bool, help='USE_GPU?', default=False)
parser.add_argument('-alz', type=str2bool, help='Actualize?', default=False)
parser.add_argument('-scheme', type=str, help='Scheme?', default='standard')
parser.add_argument('-cmd_vel', type=str2bool, help='Switch to Velocity commands?', default=True)
parser.add_argument('-ps', type=str, help='Parameter Sharing Scheme: 1. none (heterogenous) 2. full (homogeneous) 3. trunk (shared trunk - similar to multi-headed)?', default='none')

RANDOM_BASELINE = False

'''
####################
####################
README:
For heterogeneous: play with hyper parameters in CONFIG: "fire_truck_uav_long_range_lidar"
####################
####################
'''

class ConfigSettings:
	def __init__(self, popnsize):

		self.env_choice = vars(parser.parse_args())['env']
		self.action_space = vars(parser.parse_args())['action_space']

		config = vars(parser.parse_args())['config']
		self.config = config
		self.reward_scheme = vars(parser.parse_args())['reward']
		#Global subsumes local or vice-versa?
		####################### NIPS EXPERIMENTS SETUP #################
		if popnsize > 0: #######MERL or EA
			self.is_lsg = False
			self.is_proxim_rew = True

		else: #######TD3 or MADDPG
			if self.reward_scheme == 'mixed':
				self.is_lsg = True
				self.is_proxim_rew = True
			elif self.reward_scheme == 'global':
				self.is_lsg = True
				self.is_proxim_rew = False
			else:
				sys.exit('Incorrect Reward Scheme')

		self.is_gsl = False
		self.cmd_vel = vars(parser.parse_args())['cmd_vel']

		# ROVER DOMAIN
		if self.env_choice == 'rover_loose' or self.env_choice == 'rover_heterogeneous' or self.env_choice == 'rover_tight' or self.env_choice == 'rover_trap':  # Rover Domain


			if config == 'two_test':
				# Rover domain
				self.dim_x = self.dim_y = 10
				self.obs_radius = self.dim_x * 10


				self.act_dist = 2
				self.angle_res = 10
				self.num_poi = 2
				self.num_agents = 2
				self.ep_len = 30
				self.poi_rand = 1
				self.coupling = 2
				self.rover_speed = 1
				self.sensor_model = 'closest' # takes the one closest to the POI

			elif config == 'nav':
				# Rover domain
				self.dim_x = self.dim_y = 30; self.obs_radius = self.dim_x * 10; self.act_dist = 2; self.rover_speed = 1; self.sensor_model = 'closest'
				self.angle_res = 10
				self.num_poi = 10
				self.num_agents = 1
				self.ep_len = 50
				self.poi_rand = 1
				self.coupling = 1


			##########LOOSE##########
			elif config == '3_1':
				# Rover domain
				self.dim_x = self.dim_y = 30;  self.act_dist = 3; self.rover_speed = 1; self.sensor_model = 'closest'
				self.angle_res = 10
				self.num_poi = 3
				self.num_agent_types = 1  # heterogeneous agents types
				self.num_agents_per_type = 3
				self.num_agents = self.num_agent_types * self.num_agents_per_type
				obs = []
				for i in range(self.num_agent_types):
					obs.append(self.dim_x * 10 / (i + 1))

				self.obs_radius = obs
				self.obs_radius = obs
				self.ep_len = 50
				self.poi_rand = 1
				self.coupling = 1

				print("Configuration:", "Number of agents- ", self.num_agents, "Agents types- ", self.num_agent_types, "Number of POIs- ", self.num_poi)


			##########TIGHT##########


			elif config == 'fire_truck_uav':
				# Rover domain
				self.dim_x = self.dim_y = 20;
				#self.obs_radius = self.dim_x * 10;
				self.act_dist = 3;
				self.rover_speed = 1;
				self.sensor_model = 'closest'
				self.angle_res = 10
				self.num_poi = 4

				self.num_agent_types = 2  # todo: for firetruck and UAVs (type: 0 for UAV and type: 1 for firetruck)
				self.num_agents_per_type = 4


				self.num_agents = self.num_agent_types * self.num_agents_per_type
				obs = []
				for i in range(self.num_agent_types):
					obs.append(self.dim_x * 10/(i+1)) # fixme: change the observation radius to much lesser value

				self.obs_radius = obs
				self.ep_len = 50
				self.poi_rand = 1
				self.coupling = 2

				print("Configuration:", "Number of agents- ", self.num_agents, "Agents types- ", self.num_agent_types, "Number of POIs- ", self.num_poi)


			############ when we need 2 firertrucks with 1 UAV
			elif config == 'fire_truck_uav_more': # needs one UAV and 2 rovers
				# Rover domain
				self.dim_x = self.dim_y = 20;
				#self.obs_radius = self.dim_x * 10;
				self.act_dist = 3;
				self.rover_speed = 1;
				self.sensor_model = 'closest'
				self.angle_res = 10
				self.num_poi = 4

				self.num_agent_types = 2  # todo: for firetruck and UAVs (ID: 0 for UAV and ID: 1 for firetruck)
				self.num_agents_per_type = 4


				self.num_agents = self.num_agent_types * self.num_agents_per_type
				obs = []
				for i in range(self.num_agent_types):
					obs.append(self.dim_x * 10/(i+1)) # fixme: change the observation radius to much lesser value

				self.obs_radius = obs
				self.ep_len = 50
				self.poi_rand = 1
				#self.coupling = 2

				# self.coupling = 4
				coupling_factor = [0 for _ in range(self.num_agent_types)]
				coupling_factor[0] = 1
				coupling_factor[1] = 2

				self.coupling = coupling_factor

				print("Configuration:", "Number of agents- ", self.num_agents, "Agents types- ", self.num_agent_types, "Number of POIs- ", self.num_poi)

			######### Trying to simulate self driving cars which has various lidars, several cheap oneS with short range,
			######### and then one long range lidar, which gets activated only when required
			elif config == 'fire_truck_uav_long_range_lidar': # just one resolution angle has a long range, others are short
				# Rover domain
				self.dim_x = self.dim_y = 20;
				#self.obs_radius = self.dim_x * 10;
				self.act_dist = 3; # fixme: changed from 3
				self.rover_speed = 1;
				self.sensor_model = 'closest'
				self.angle_res = 10# fixme: changed this
				self.num_poi = 4

				self.num_agent_types = 2  # for firetruck and UAVs (type: 0 for UAV and type: 1 for firetruck)
				self.num_agents_per_type = 4

				self.num_agents = self.num_agent_types * self.num_agents_per_type
				obs = []
				percentage = 40  # fixme: added for comparison purpose, also need to change from 5 to 2

				obs.append(2*self.dim_x) # for UAV
				#obs.append(np.sqrt(2)*self.dim_x/2) # for fire truck
				obs.append(np.sqrt((percentage / (100 * 3.14))) * self.dim_x)
				#for i in range(self.num_agent_types):
				#	obs.append(2*self.dim_x * 10/(i+1))

				self.obs_radius = obs
				#self.long_range = 2*self.dim_x
				self.long_range = np.sqrt((percentage / (100 * 3.14))) * self.dim_x # fixme: currently no long range beam present, so this is same as obs of short beam
				self.ep_len = 50
				self.poi_rand = 1
				#self.coupling = 2

				coupling_factor = [0 for _ in range(self.num_agent_types)]
				coupling_factor[0] = 1
				coupling_factor[1] = 2

				self.coupling = coupling_factor

				print("Configuration:", "Number of agents- ", self.num_agents, "Agents types- ", self.num_agent_types, "Number of POIs- ", self.num_poi)

			elif config == '4_2':
				# Rover domain
				self.dim_x = self.dim_y = 20;
				#self.obs_radius = self.dim_x * 10;
				self.act_dist = 3;
				self.rover_speed = 1;
				self.sensor_model = 'closest'
				self.angle_res = 10
				self.num_poi = 4

				self.num_agent_types = 2  # todo: for more number of agents
				self.num_agents_per_type = 2


				self.num_agents = self.num_agent_types * self.num_agents_per_type
				obs = []
				for i in range(self.num_agent_types):
					obs.append(self.dim_x * 10/(i+1))

				self.obs_radius = obs
				self.ep_len = 50
				self.poi_rand = 1
				self.coupling = 2

				print("Configuration:", "Number of agents- ", self.num_agents, "Agents types- ", self.num_agent_types, "Number of POIs- ", self.num_poi)


			elif config == '6_3':
				# Rover domain
				self.dim_x = self.dim_y = 20; self.act_dist = 3; self.rover_speed = 1; self.sensor_model = 'closest'
				self.angle_res = 10
				self.num_poi = 4


				self.num_agent_types = 2  # todo: for more number of agents
				self.num_agents_per_type = 3

				self.num_agents = self.num_agent_types * self.num_agents_per_type

				obs = []
				for i in range(self.num_agent_types):
					obs.append(self.dim_x * 10 / (i + 1))

				self.obs_radius = obs

				self.ep_len = 50
				self.poi_rand = 1
				self.coupling = 3

				print("Configuration:", "Number of agents- ", self.num_agents, "Agents types- ", self.num_agent_types, "Number of POIs- ", self.num_poi)


			elif config == '8_4':
				# Rover domain
				self.dim_x = self.dim_y = 20; self.obs_radius = self.dim_x * 10; self.act_dist = 3; self.rover_speed = 1; self.sensor_model = 'closest'
				self.angle_res = 10
				self.num_poi = 4


				self.num_agent_types = 2  # todo: for more number of agents
				self.num_agents_per_type = 4

				self.num_agents = self.num_agent_types * self.num_agents_per_type

				obs = []
				for i in range(self.num_agent_types):
					obs.append(self.dim_x * 10 / (i + 1))

				self.obs_radius = obs

				self.ep_len = 50
				self.poi_rand = 1
				self.coupling = 4

			elif config == '10_5':
				# Rover domain
				self.dim_x = self.dim_y = 20;  self.act_dist = 3; self.rover_speed = 1; self.sensor_model = 'closest'
				self.angle_res = 10
				self.num_poi = 4
				self.num_agents = 10
				self.ep_len = 50
				self.poi_rand = 1
				self.coupling = 5

			elif config == '12_6':
				# Rover domain
				self.dim_x = self.dim_y = 20; self.act_dist = 3; self.rover_speed = 1; self.sensor_model = 'closest'
				self.angle_res = 10
				self.num_poi = 4

				self.num_agent_types = 2  # todo: for more number of agents
				self.num_agents_per_type = 6

				self.num_agents = self.num_agent_types * self.num_agents_per_type

				obs = []
				for i in range(self.num_agent_types):
					obs.append(self.dim_x * 10 / (i + 1))

				self.obs_radius = obs

				self.ep_len = 50
				self.ep_len = 50
				self.poi_rand = 1
				self.coupling = 6

			elif config == '14_7':
				# Rover domain
				self.dim_x = self.dim_y = 20; self.obs_radius = self.dim_x * 10; self.act_dist = 3; self.rover_speed = 1; self.sensor_model = 'closest'
				self.angle_res = 10
				self.num_poi = 4
				self.num_agents = 14
				self.ep_len = 50
				self.poi_rand = 1
				self.coupling = 7



			else:
				sys.exit('Unknown Config')

			#Fix Harvest Period and coupling given some config choices

			if self.env_choice == "rover_trap": self.harvest_period = 3
			else: self.harvest_period = 1

			if self.env_choice == "rover_loose": self.coupling = 1 #Definiton of a Loosely coupled domain



		###### fixme: removed this following block
		'''
		elif self.env_choice == 'rover_heterogeneous':
			pass
		

		else:
			sys.exit('Unknown Environment Choice')
		'''

class Parameters:
	def __init__(self):

		# Transitive Algo Params
		self.popn_size = vars(parser.parse_args())['popsize']
		self.rollout_size = vars(parser.parse_args())['rollsize']
		self.num_evals = vars(parser.parse_args())['evals']
		self.frames_bound = int(vars(parser.parse_args())['frames'] * 1000000)
		self.actualize = vars(parser.parse_args())['alz'] # todo: what is this?
		self.priority_rate = vars(parser.parse_args())['pr']
		self.use_gpu = torch.cuda.is_available()
		self.seed = vars(parser.parse_args())['seed']
		self.ps = vars(parser.parse_args())['ps']
		self.is_matd3 = vars(parser.parse_args())['matd3']
		self.is_maddpg = vars(parser.parse_args())['maddpg']
		assert  self.is_maddpg * self.is_matd3 == 0 #Cannot be both True
		self.use_dpp = vars(parser.parse_args())['dpp']  # 'multipoint' vs 'standard'
		self.action_space = vars(parser.parse_args())['action_space'] # todo: change for same action space

		# Env domain
		self.config = ConfigSettings(self.popn_size)

		# Fairly Stable Algo params
		self.hidden_size = 50 #fixme: changed from 100
		self.algo_name = vars(parser.parse_args())['algo']
		self.actor_lr = 5e-3
		self.critic_lr = 1e-3
		self.tau = 1e-3
		self.init_w = True
		self.gradperstep = vars(parser.parse_args())['gradperstep']
		self.gamma = 0.5 if self.popn_size > 0 else 0.97
		self.batch_size = 512
		self.buffer_size = 100000
		#self.buffer_size = 10
		self.filter_c = vars(parser.parse_args())['filter_c']
		self.reward_scaling = 10.0 # TODO: why is this required?

		self.action_loss = False
		self.policy_ups_freq = 2
		self.policy_noise = True
		self.policy_noise_clip = 0.4

		# SAC
		self.alpha = 0.2
		self.target_update_interval = 1

		# NeuroEvolution stuff

		self.scheme = vars(parser.parse_args())['scheme']  # 'multipoint' vs 'standard'
		self.crossover_prob = 0.1
		self.mutation_prob = 0.9
		self.extinction_prob = 0.005  # Probability of extinction event
		self.extinction_magnitude = 0.5  # Probabilty of extinction for each genome, given an extinction event
		self.weight_clamp = 1000000
		self.mut_distribution = 1  # 1-Gaussian, 2-Laplace, 3-Uniform
		self.lineage_depth = 10
		self.ccea_reduction = "leniency"
		self.num_anchors = 5
		self.num_elites = 4
		self.num_blends = int(0.15 * self.popn_size)

		# Dependents
		if self.config.env_choice == 'rover_loose' or self.config.env_choice == 'rover_tight' or self.config.env_choice == 'rover_trap' or self.config.env_choice == 'rover_heterogeneous':  # Rover Domain
			self.state_dim = int(360*(1+self.config.num_agent_types) / self.config.angle_res) + 1
			if self.config.cmd_vel: self.state_dim += 2
			self.action_dim = 2
		elif self.config.env_choice == 'motivate':  # MultiWalker Domain
			self.state_dim = int(720 / self.config.angle_res) + 3
			self.action_dim = 2
		elif self.config.env_choice == 'multiwalker':  # MultiWalker Domain
			self.state_dim = 33
			self.action_dim = 4
		elif self.config.env_choice == 'cassie':  # Cassie Domain
			self.state_dim = 82 if self.config.config == 'adaptive' else 80
			self.action_dim = 10
			self.hidden_size = 200
			self.gamma = 0.99
			self.buffer_size = 1000000



		elif self.config.env_choice == 'hyper':  # Cassie Domain
			self.state_dim = 20
			self.action_dim = 2

		elif self.config.env_choice == 'pursuit':  # Cassie Domain
			self.state_dim = 213
			self.action_dim = 2
		elif self.config.env_choice == 'maddpg_envs':  # Cassie Domain
			self.state_dim = 18
			self.action_dim = 2
			self.hidden_size = 100
		else:
			sys.exit('Unknown Environment Choice')

		# if self.config.env_choice == 'motivate':
		# 	self.hidden_size = 100
		# 	self.buffer_size = 100000
		# 	self.batch_size = 128
		# 	self.gamma = 0.9
		# 	self.num_anchors=7


		self.num_test = 20
		self.test_gap = 5

		# Save Filenames
		self.savetag = vars(parser.parse_args())['savetag'] + \
		               'pop' + str(self.popn_size) + \
		               '_roll' + str(self.rollout_size) + \
		               '_env' + str(self.config.env_choice) + '_' + str(self.config.config) + \
						'_action_' + str(self.action_space) + \
			            '_seed' + str(self.seed) + \
						'-reward' + str(self.config.reward_scheme) +\
					   ('_alz' if self.actualize else '') + \
		               ('_gsl' if self.config.is_gsl else '') + \
		               ('_multipoint' if self.scheme == 'multipoint' else '') + \
		               ('_matd3' if self.is_matd3 else '') + \
		               ('_maddpg' if self.is_maddpg else '') +\
					   ('_dpp' if self.use_dpp else '')

		# '_pr' + str(self.priority_rate)
		# '_algo' + str(self.algo_name) + \
		# '_evals' + str(self.num_evals) + \
		# '_seed' + str(SEED)
		#'_filter' + str(self.filter_c)

		self.save_foldername = 'R_MERL/'
		if not os.path.exists(self.save_foldername): os.makedirs(self.save_foldername)
		self.metric_save = self.save_foldername + 'metrics/'
		self.model_save = self.save_foldername + 'models/'
		self.aux_save = self.save_foldername + 'auxiliary/'
		if not os.path.exists(self.save_foldername): os.makedirs(self.save_foldername)
		if not os.path.exists(self.metric_save): os.makedirs(self.metric_save)
		if not os.path.exists(self.model_save): os.makedirs(self.model_save)
		if not os.path.exists(self.aux_save): os.makedirs(self.aux_save)

		self.critic_fname = 'critic_' + self.savetag
		self.actor_fname = 'actor_' + self.savetag
		self.log_fname = 'reward_' + self.savetag
		self.best_fname = 'best_' + self.savetag


class MERL:
	"""Policy Gradient Algorithm main object which carries out off-policy learning using policy gradient
	   Encodes all functionalities for 1. TD3 2. DDPG 3.Trust-region TD3/DDPG 4. Advantage TD3/DDPG

			Parameters:
				args (int): Parameter class with all the parameters

			"""

	def __init__(self, args):
		self.args = args

		######### Initialize the Multiagent Team of agents ########
		if self.args.ps == 'full' or self.args.ps == 'trunk':
			self.agents = [Agent(self.args, id)] #todo: is it one agent or more>? is it just agent? sharing all parameters
		elif self.args.ps == 'none':
			self.agents = [Agent(self.args, id) for id in range(self.args.config.num_agents)] # neural network for each agent
		else: sys.exit('Incorrect PS choice')
		self.test_agent = TestAgent(self.args, 991)

		###### Buffer and Model Bucket as references to the corresponding agent's attributes ####
		if args.ps == "trunk": self.buffer_bucket = [buffer.tuples for buffer in self.agents[0].buffer]
		else: self.buffer_bucket = [ag.buffer.tuples for ag in self.agents]

		# Specifying 3 different networks for evo, PG and test rollouts
		self.popn_bucket = [ag.popn for ag in self.agents]
		self.rollout_bucket = [ag.rollout_actor for ag in self.agents]
		self.test_bucket = self.test_agent.rollout_actor

		######### EVOLUTIONARY WORKERS ############
		if self.args.popn_size > 0:
			self.evo_task_pipes = [Pipe() for _ in range(args.popn_size * args.num_evals)] # evals for computing the fitness
			self.evo_result_pipes = [Pipe() for _ in range(args.popn_size * args.num_evals)]
			self.evo_workers = [Process(target=rollout_worker, args=(
				self.args, i, 'evo', self.evo_task_pipes[i][1], self.evo_result_pipes[i][0],
				self.buffer_bucket, self.popn_bucket, True, RANDOM_BASELINE)) for i in
			                    range(args.popn_size * args.num_evals)] # rollout for pop_size*num_evals, # popn_bucket is the neural network for evo
			for worker in self.evo_workers: worker.start()

		######### POLICY GRADIENT WORKERS ############
		if self.args.rollout_size > 0:
			self.pg_task_pipes = Pipe()
			self.pg_result_pipes = Pipe()
			self.pg_workers = [
				Process(target=rollout_worker, args=(self.args, 0, 'pg', self.pg_task_pipes[1], self.pg_result_pipes[0],
				                                     self.buffer_bucket, self.rollout_bucket,
				                                     self.args.rollout_size > 0, RANDOM_BASELINE))] # rollout_bucket is the neural network for evo
			for worker in self.pg_workers: worker.start()

		######### TEST WORKERS ############
		self.test_task_pipes = Pipe()
		self.test_result_pipes = Pipe()
		self.test_workers = [Process(target=rollout_worker,
		                             args=(self.args, 0, 'test', self.test_task_pipes[1], self.test_result_pipes[0],
		                                   None, self.test_bucket, False, RANDOM_BASELINE))] # test_bucket is the neural network for evo
		for worker in self.test_workers: worker.start()

		#### STATS AND TRACKING WHICH ROLLOUT IS DONE ######
		self.best_score = -999;
		self.total_frames = 0;
		self.gen_frames = 0;
		self.test_trace = []

	def make_teams(self, num_agents, popn_size, num_evals):

		temp_inds = []
		for _ in range(num_evals): temp_inds += list(range(popn_size)) # this gives [0,1,2,3... (pop_size-1), 0,1,2,3.., (pop_size-1), for num_evals times]

		all_inds = [temp_inds[:] for _ in range(num_agents)] # repeating the above list for all agents [[0,1,2,3...], [0,1,2,3,...]..[]]
		# for _ in range(num_evals):
		# 	for ag in range(num_agents):
		# 		all_inds[ag] += list(range(popn_size))

		for entry in all_inds: random.shuffle(entry)

		teams = [[entry[i] for entry in all_inds] for i in range(popn_size * num_evals)] # number of teams = pop_size * number of evals

		return teams

	def train(self, gen, test_tracker):
		"""Main training loop to do rollouts and run policy gradients

			Parameters:
				gen (int): Current epoch of training

			Returns:
				None
		"""

		# Test Rollout
		if gen % self.args.test_gap == 0:
			self.test_agent.make_champ_team(self.agents)  # Sync the champ policies into the TestAgent
			self.test_task_pipes[0].send("START") # sending START signal

		# Figure out teams for Coevolution

		if self.args.ps == 'full' or self.args.ps == 'trunk':
			teams = [[i] for i in list(range(args.popn_size))] # returns [[0], [1], [2]..] Homogeneous case is just the popn as a list of lists to maintain compatibility
		else:
			teams = self.make_teams(args.config.num_agents, args.popn_size, args.num_evals)  # Heterogeneous Case
			# returns [[0,1,2,3..], [2,3,1,0...], ...] shuffled teams of agents, like 1st agent is from pop k, and so on....

		#teams = self.make_teams(args.config.num_agents, args.popn_size, args.num_evals)  # Heterogeneous Case

		########## START EVO ROLLOUT ##########
		if self.args.popn_size > 0:
			for pipe, team in zip(self.evo_task_pipes, teams):
				pipe[0].send(team)# sending team signal

		########## START POLICY GRADIENT ROLLOUT ##########
		if self.args.rollout_size > 0 and not RANDOM_BASELINE:
			# Synch pg_actors to its corresponding rollout_bucket
			for agent in self.agents: agent.update_rollout_actor() # agents denote different neural network

			# Start rollouts using the rollout actors
			self.pg_task_pipes[0].send('START')  # Index 0 for the Rollout bucket

			############ POLICY GRADIENT UPDATES #########
			# Spin up threads for each agent
			# Only PG will update, evolutionary will evolve
			threads = [threading.Thread(target=agent.update_parameters, args=()) for agent in self.agents]

			# Start threads
			for thread in threads: thread.start()

			# Join threads
			for thread in threads: thread.join()

		all_fits = []
		####### JOIN EVO ROLLOUTS ########
		if self.args.popn_size > 0:
			for pipe in self.evo_result_pipes: # for each population
				entry = pipe[1].recv()
				team = entry[0]; # team members
				fitness = entry[1][0]; # list of fitness values for each evaluation of each team
				frames = entry[2]

				# so here, we are keeping a track of agent's ID and from which pop it came from
				# what average fitness each agent gets in each population, so it means agent corresponding to which population id gets
				# what reward when teamed up with agents picked randomly from other population, so each agent will have fitness according
				# to the length of the population
				for agent_id, popn_id in enumerate(team): self.agents[agent_id].fitnesses[popn_id].append(
					utils.list_mean(fitness))  ##Assign average of all fitness values of each evaluation to agent in that particular team
				#print("##########", fitness)
				all_fits.append(utils.list_mean(fitness))
				self.total_frames += frames

		####### JOIN PG ROLLOUTS ########
		pg_fits = []
		if self.args.rollout_size > 0 and not RANDOM_BASELINE:
			entry = self.pg_result_pipes[1].recv() # for all the PG rollouts (50 in this case), it will store different fitness value
			pg_fits = entry[1][0]
			self.total_frames += entry[2]

		####### JOIN TEST ROLLOUTS ########
		test_fits = []
		if gen % self.args.test_gap == 0:
			entry = self.test_result_pipes[1].recv()
			test_fits = entry[1][0]
			test_tracker.update([mod.list_mean(test_fits)], self.total_frames)
			self.test_trace.append(mod.list_mean(test_fits))

		# Evolution Step
		for agent in self.agents:
			agent.evolve() # selection, mutation happens

		#Save models periodically
		if gen % 20 == 0:
			for id, test_actor in enumerate(self.test_agent.rollout_actor):
				torch.save(test_actor.state_dict(), self.args.model_save + str(id) + '_' + self.args.actor_fname)
			print("Models Saved")

		return all_fits, pg_fits, test_fits


if __name__ == "__main__":
	args = Parameters()  # Create the Parameters class
	test_tracker = utils.Tracker(args.metric_save, [args.log_fname], '.csv')  # Initiate tracker
	torch.manual_seed(args.seed);
	np.random.seed(args.seed);
	random.seed(args.seed)  # Seeds
	if args.config.env_choice == 'hyper': from envs.hyper.PowerPlant_env import Fast_Simulator  # Main Module needs access to this class for some reason

	# INITIALIZE THE MAIN AGENT CLASS
	ai = MERL(args)
	print('Running ', args.config.env_choice, 'with config ', args.config.config, ' State_dim:', args.state_dim,
	      'Action_dim', args.action_dim)
	time_start = time.time()

	###### TRAINING LOOP ########
	for gen in range(1, 10000000000):  # RUN VIRTUALLY FOREVER

		# ONE EPOCH OF TRAINING
		popn_fits, pg_fits, test_fits = ai.train(gen, test_tracker)

		# PRINT PROGRESS
		print('Ep:/Frames', gen, '/', ai.total_frames, 'Popn stat:', mod.list_stat(popn_fits), 'PG_stat:',
		      mod.list_stat(pg_fits),
		      'Test_trace:', [pprint(i) for i in ai.test_trace[-5:]], 'FPS:',
		      pprint(ai.total_frames / (time.time() - time_start)), 'Evo', args.scheme, 'PS:', args.ps
		      )

		if gen % 5 == 0:
			print()
			print('Test_stat:', mod.list_stat(test_fits), 'SAVETAG:  ', args.savetag)
			print('Weight Stats: min/max/average', pprint(ai.test_bucket[0].get_norm_stats()))
			print('Buffer Lens:', [ag.buffer[0].__len__() for ag in ai.agents] if args.ps == 'trunk' else [ag.buffer.__len__() for ag in ai.agents])
			print()

		if gen % 10 == 0 and args.rollout_size > 0:
			print()
			print('Q', pprint(ai.agents[0].algo.q))
			print('Q_loss', pprint(ai.agents[0].algo.q_loss))
			print('Policy', pprint(ai.agents[0].algo.policy_loss))
			if args.algo_name == 'TD3' and not args.is_matd3 and not args.is_maddpg:
				print('Alz_Score', pprint(ai.agents[0].algo.alz_score))
				print('Alz_policy', pprint(ai.agents[0].algo.alz_policy))

			if args.algo_name == 'SAC':
				print('Val', pprint(ai.agents[0].algo.val))
				print('Val_loss', pprint(ai.agents[0].algo.value_loss))
				print('Mean_loss', pprint(ai.agents[0].algo.mean_loss))
				print('Std_loss', pprint(ai.agents[0].algo.std_loss))

			# Buffer Stats
			if args.ps != 'trunk':
				print('R_mean:', [agent.buffer.rstats['mean'] for agent in ai.agents])
				print('G_mean:', [agent.buffer.gstats['mean'] for agent in ai.agents])

			print('########################################################################')

		if ai.total_frames > args.frames_bound:
			break

	###Kill all processes
	try: ai.pg_task_pipes[0].send('TERMINATE')
	except: None
	try: ai.test_task_pipes[0].send('TERMINATE')
	except: None
	try:
		for p in ai.evo_task_pipes: p[0].send('TERMINATE')
	except: None
	print('Finished Running ', args.savetag)
	exit(0)
