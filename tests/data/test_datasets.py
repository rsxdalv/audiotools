import numpy as np
import torch

import audiotools
from audiotools import AudioSignal
from audiotools.data import transforms as tfm

audiotools.data.preprocess.create_csv(
    audiotools.util.find_audio("tests/audio/spk", ext=["wav"]),
    "tests/audio/spk.csv",
    loudness=True,
)


def test_static_shared_args():
    dataset = audiotools.data.datasets.CSVDataset(
        44100,
        n_examples=100,
        csv_files=["tests/audio/spk.csv"],
    )

    for nw in (0, 1, 2):
        dataloader = torch.utils.data.DataLoader(
            dataset,
            batch_size=1,
            num_workers=nw,
            collate_fn=dataset.collate,
        )

        targets = {"dur": [dataloader.dataset.duration], "sr": [44100]}
        observed = {"dur": [], "sr": []}

        sample_rates = [8000, 16000, 44100]

        for batch in dataloader:
            dur = np.random.rand()
            sr = int(np.random.choice(sample_rates))

            # Change attributes in the shared dict.
            # Later we'll make sure they actually worked.
            dataloader.dataset.duration = dur
            dataloader.dataset.sample_rate = sr

            # Record observations from the batch and the signal.
            targets["dur"].append(dur)
            observed["dur"].append(batch["signal"].signal_duration)

            targets["sr"].append(sr)
            observed["sr"].append(batch["signal"].sample_rate)

        # You aren't guaranteed that every requested attribute setting gets to every
        # worker in time, but you can expect that every output attribute
        # is in the requested attributes, and that it happens at least twice.
        for k in targets:
            _targets = targets[k]
            _observed = observed[k]

            num_succeeded = 0
            for val in np.unique(_observed):
                assert np.any(np.abs(np.array(_targets) - val) < 1e-3)
                num_succeeded += 1

            assert num_succeeded >= 2


# This transform just adds the ID of the object, so we
# can see if it's the same across processes.
class IDTransform(audiotools.data.transforms.BaseTransform):
    def __init__(self):
        super().__init__(["id"])
        self.id = 1

    def _instantiate(self, state):
        return {"id": self.id}


def test_shared_transform():
    transform = IDTransform()
    dataset = audiotools.data.datasets.CSVDataset(
        44100,
        n_examples=100,
        csv_files=["tests/audio/spk.csv"],
        transform=transform,
    )

    for nw in (0, 1, 2):
        dataloader = torch.utils.data.DataLoader(
            dataset,
            batch_size=1,
            num_workers=nw,
            collate_fn=dataset.collate,
        )

        collected_ids = []

        for batch in dataloader:
            batch = dataset.augment(batch)
            collected_ids.append(batch["IDTransform"]["id"])

        collected_ids = list(set([x.item() for x in collected_ids]))
        assert len(collected_ids) == 1


def test_csv_dataset():
    transform = tfm.Silence(prob=0.5)
    dataset = audiotools.data.datasets.CSVDataset(
        44100,
        n_examples=100,
        csv_files=["tests/audio/spk.csv"],
        transform=transform,
    )
    dataloader = torch.utils.data.DataLoader(
        dataset,
        batch_size=16,
        num_workers=0,
        collate_fn=dataset.collate,
    )
    for batch in dataloader:
        batch = dataset.transform(batch)
        mask = batch["Silence"]["mask"]

        zeros = torch.zeros_like(batch["signal"][mask].audio_data)
        original = batch["original"][~mask].audio_data

        assert torch.allclose(batch["signal"][mask].audio_data, zeros)
        assert torch.allclose(batch["signal"][~mask].audio_data, original)
