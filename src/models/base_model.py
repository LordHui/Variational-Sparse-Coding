import torch
from torchvision.utils import save_image
from pathlib import Path
from glob import glob
from logger import Logger


class VariationalBaseModel():
    def __init__(self, dataset, width, height, hidden_sz, latent_sz, 
                 learning_rate, device, log_interval):
        self.dataset = dataset
        self.width = width
        self.height = height
        self.input_sz = width * height
        self.hidden_sz = hidden_sz
        self.latent_sz = latent_sz
        
        self.lr = learning_rate
        self.device = device
        self.log_interval = log_interval
        
        # To be implemented by subclasses
        self.model = None
        self.optimizer = None        
    
    
    def loss_function(self):
        raise NotImplementedError
    
    
    def step(self, data, train=False):
        if train:
            self.optimizer.zero_grad()
        output = self.model(data)
        loss = self.loss_function(data, *output)
        if train:
            loss.backward()
            self.optimizer.step()
        return loss.item()
    
    
    # Run training iterations and report results
    def train(self, train_loader, epoch):
        self.model.train()
        train_loss = 0
        for batch_idx, (data, _) in enumerate(train_loader):
            data = data.to(self.device)      
            loss = self.step(data, train=True)
            train_loss += loss
            if batch_idx % self.log_interval == 0:
                print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}' \
                      .format(epoch, batch_idx * len(data), 
                              len(train_loader.dataset),
                              100. * batch_idx / len(train_loader),
                              loss / len(data)))

        print('====> Epoch: {} Average loss: {:.4f}'.format(
              epoch, train_loss / len(train_loader.dataset)))
        
        
    # Returns the VLB for the test set
    def test(self, test_loader, epoch):
        self.model.eval()
        test_loss = 0
        with torch.no_grad():
            for data, _ in test_loader:
                data = data.to(self.device)
                test_loss += self.step(data, train=False)
                
        VLB = test_loss / len(test_loader)
        ## Optional to normalize VLB on testset
        name = self.model.__class__.__name__
        test_loss /= len(test_loader.dataset) 
        print(f'====> Test set loss: {test_loss:.4f} - VLB-{name} : {VLB:.4f}')
        return test_loss
    
    
    #Auxiliary function to continue training from last trained models
    def load_last_model(self, checkpoints_path):
        name = self.model.__class__.__name__
        # Search for all previous checkpoints
        models = glob(f'{checkpoints_path}/*.pth')
        model_ids = []
        for f in models:
            # modelname_dataset_startepoch_epochs_latentsize_lr_epoch
            run_name = Path(f).stem
            model_name, dataset, _, _, latent_sz, _, epoch = run_name.split('_')
            if model_name == name and dataset == self.dataset and \
               int(latent_sz) == self.latent_sz:
                model_ids.append((int(epoch), f))
                
        # If no checkpoints available
        if len(model_ids) == 0:
            print(f'Training {name} model from scratch...')
            return 1

        # Load model from last checkpoint 
        start_epoch, last_checkpoint = max(model_ids, key=lambda item: item[0])
        print('Last checkpoint: ', last_checkpoint)
        self.model.load_state_dict(torch.load(last_checkpoint))
        print(f'Loading {name} model from last checkpoint ({start_epoch})...')

        return start_epoch + 1
    
    
    def update_(self):
        pass
    
    
    def run_training(self, train_loader, test_loader, epochs, 
                     report_interval, sample_sz=64,
                     checkpoints_path='../results/checkpoints',
                     logs_path='../results/logs',
                     images_path='../results/images'):
        
        start_epoch = self.load_last_model(checkpoints_path)
        name = self.model.__class__.__name__
        run_name = f'{name}_{self.dataset}_{start_epoch}_{epochs}_' \
                   f'{self.latent_sz}_{str(self.lr).replace(".", "-")}'
        logger = Logger(f'{logs_path}/{run_name}')
        print(f'Training {name} model...')
        for epoch in range(start_epoch, start_epoch + epochs):
            train_loss = self.train(train_loader, epoch)
            test_loss = self.test(test_loader, epoch)
            # Store log
            logger.scalar_summary(train_loss, test_loss, epoch)
            # Optional update
            self.update_()
            # For each report interval store model and save images
            if epoch % report_interval == 0:
                with torch.no_grad():
                    ## Generate random samples
                    sample = torch.randn(sample_sz, self.latent_sz) \
                                  .to(self.device)
                    sample = self.model.decode(sample).cpu()
                    ## Store sample plots
                    save_image(sample.view(sample_sz, 1, self.width,
                                           self.height),
                               f'{images_path}/sample_{run_name}_{epoch}.png')
                    ## Store Model
                    torch.save(self.model.state_dict(), 
                               f'{checkpoints_path}/{run_name}_{epoch}.pth')