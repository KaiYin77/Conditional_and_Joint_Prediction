import os; os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
import sys
import argparse
import datetime

import torch; torch.autograd.set_detect_anomaly(True)
from torch import nn
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter

import pandas as pd
from tqdm import tqdm
from importlib import import_module 
import env

### Argument parser
parser = argparse.ArgumentParser()
parser.add_argument(
        "--resume", 
        help="resume from a checkpoint", 
        default="", 
        type=str
)
parser.add_argument(
        "--debug",
        help="debug mode",
        action='store_true',
)
args = parser.parse_args()
### Setting data path
root_dir = env.SERVER_DOCKER['waymo']
raw_dir = root_dir + 'raw/validation/'
val_raw_dir = root_dir + 'raw/validation/'
processed_dir = root_dir + 'processed/interactive/validation/'
val_processed_dir = root_dir + 'processed/interactive/validation/'

file_names = [f for f in os.listdir(raw_dir)]
val_file_names = [f for f in os.listdir(val_raw_dir)]

os.makedirs(processed_dir, exist_ok=True)

### GPU utilization
device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')

### Create the model
model = import_module(f"model")
config, Dataset, my_collate, net, opt = model.get_model()
BATCHSIZE = config['batch_size']

### Resume training state
CHECKPOINT = 0
EPOCHS = config['epochs']
OBSERVED = config['observed']
TOTAL = config['total']

save_dir = config["save_dir"]
os.makedirs(save_dir, exist_ok=True)

if args.resume:
    ### Load previous weight
    weight = os.path.join(config['save_dir'], args.resume)
    state_dict = torch.load(weight)
    net.load_state_dict(state_dict)
    CHECKPOINT = int(args.resume[:-5])

### Prepare for model
net.train()
epochs = range(CHECKPOINT, EPOCHS)
criterion = nn.CrossEntropyLoss()

def train_waymo(logger):
    for epoch in epochs:
        running_loss = 0.0
        steps = 0
        correct = 0
        file_iter = tqdm(file_names)
        for i, file in enumerate(file_iter):
            file_idx = file[-14:-9]
            raw_path = raw_dir+file
            dataset = Dataset(raw_path, config, processed_dir+f'{file_idx}')
            dataloader = DataLoader(dataset, batch_size=BATCHSIZE, collate_fn=my_collate, num_workers=8)
            dataiter = iter(dataloader)
            for data in dataiter:
                if(data==None):
                    continue
                opt.zero_grad()
                
                outputs = net(data)
                relation_class = data['relation']
                relation_class_tensor = torch.as_tensor(relation_class).to(device)
                 
                if (args.debug): 
                    print('pred_class: ', outputs)
                    print('gt_class: ', relation_class_tensor)
                loss = criterion(outputs, relation_class_tensor)
                loss.backward()
                opt.step()
                
                conf, index = outputs.max(-1)
                if index == relation_class_tensor:
                    correct += 1

                running_loss += loss.item()
                steps += 1
            file_iter.set_description(f'Epoch: {epoch+1}, CE: {running_loss/steps}, Accuracy: {correct/steps}')
        
        logger.add_scalar('Loss', running_loss/steps, epoch) 
        torch.save(net.state_dict(), f'{save_dir}/{epoch+1}.ckpt')
def val_waymo():
    pass

def main():
    if config['dataset'] == 'waymo':
        log_dir = "logs/joint/" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        logger = SummaryWriter(log_dir)
        train_waymo(logger)
        logger.close()

if __name__ == '__main__':
    main()