from keras.src.api_export import keras_export
from keras.src.layers.preprocessing.image_preprocessing.base_image_preprocessing_layer import (  # noqa: E501
    BaseImagePreprocessingLayer,
)
from keras.src.random.seed_generator import SeedGenerator


@keras_export("keras.layers.RandomShear")
class RandomShear(BaseImagePreprocessingLayer):
    """A preprocessing layer that randomly applies shear transformations to
    images.

    This layer shears the input images along the x-axis and/or y-axis by a
    randomly selected factor within the specified range. The shear
    transformation is applied to each image independently in a batch. Empty
    regions created during the transformation are filled according to the
    `fill_mode` and `fill_value` parameters.

    Args:
        x_factor: A tuple of two floats. For each augmented image, a value
            is sampled from the provided range. If a float is passed, the
            range is interpreted as `(0, x_factor)`. Values represent a
            percentage of the image to shear over. For example, 0.3 shears
            pixels up to 30% of the way across the image. All provided values
            should be positive.
        y_factor: A tuple of two floats. For each augmented image, a value
            is sampled from the provided range. If a float is passed, the
            range is interpreted as `(0, y_factor)`. Values represent a
            percentage of the image to shear over. For example, 0.3 shears
            pixels up to 30% of the way across the image. All provided values
            should be positive.
        interpolation: Interpolation mode. Supported values: `"nearest"`,
            `"bilinear"`.
        fill_mode: Points outside the boundaries of the input are filled
            according to the given mode. Available methods are `"constant"`,
            `"nearest"`, `"wrap"` and `"reflect"`. Defaults to `"constant"`.
            - `"reflect"`: `(d c b a | a b c d | d c b a)`
                The input is extended by reflecting about the edge of the
                last pixel.
            - `"constant"`: `(k k k k | a b c d | k k k k)`
                The input is extended by filling all values beyond the edge
                with the same constant value `k` specified by `fill_value`.
            - `"wrap"`: `(a b c d | a b c d | a b c d)`
                The input is extended by wrapping around to the opposite edge.
            - `"nearest"`: `(a a a a | a b c d | d d d d)`
                The input is extended by the nearest pixel.
            Note that when using torch backend, `"reflect"` is redirected to
            `"mirror"` `(c d c b | a b c d | c b a b)` because torch does
            not support `"reflect"`.
            Note that torch backend does not support `"wrap"`.
        fill_value: A float representing the value to be filled outside the
            boundaries when `fill_mode="constant"`.
        seed: Integer. Used to create a random seed.
    """

    _USE_BASE_FACTOR = False
    _FACTOR_BOUNDS = (0, 1)
    _FACTOR_VALIDATION_ERROR = (
        "The `factor` argument should be a number (or a list of two numbers) "
        "in the range [0, 1.0]. "
    )
    _SUPPORTED_FILL_MODE = ("reflect", "wrap", "constant", "nearest")
    _SUPPORTED_INTERPOLATION = ("nearest", "bilinear")

    def __init__(
        self,
        x_factor=0.0,
        y_factor=0.0,
        interpolation="bilinear",
        fill_mode="reflect",
        fill_value=0.0,
        data_format=None,
        seed=None,
        **kwargs,
    ):
        super().__init__(data_format=data_format, **kwargs)
        self.x_factor = self._set_factor_with_name(x_factor, "x_factor")
        self.y_factor = self._set_factor_with_name(y_factor, "y_factor")

        if fill_mode not in self._SUPPORTED_FILL_MODE:
            raise NotImplementedError(
                f"Unknown `fill_mode` {fill_mode}. Expected of one "
                f"{self._SUPPORTED_FILL_MODE}."
            )
        if interpolation not in self._SUPPORTED_INTERPOLATION:
            raise NotImplementedError(
                f"Unknown `interpolation` {interpolation}. Expected of one "
                f"{self._SUPPORTED_INTERPOLATION}."
            )

        self.fill_mode = fill_mode
        self.fill_value = fill_value
        self.interpolation = interpolation
        self.seed = seed
        self.generator = SeedGenerator(seed)
        self.supports_jit = False

    def _set_factor_with_name(self, factor, factor_name):
        if isinstance(factor, (tuple, list)):
            if len(factor) != 2:
                raise ValueError(
                    self._FACTOR_VALIDATION_ERROR
                    + f"Received: {factor_name}={factor}"
                )
            self._check_factor_range(factor[0])
            self._check_factor_range(factor[1])
            lower, upper = sorted(factor)
        elif isinstance(factor, (int, float)):
            self._check_factor_range(factor)
            factor = abs(factor)
            lower, upper = [-factor, factor]
        else:
            raise ValueError(
                self._FACTOR_VALIDATION_ERROR
                + f"Received: {factor_name}={factor}"
            )
        return lower, upper

    def _check_factor_range(self, input_number):
        if input_number > 1.0 or input_number < 0.0:
            raise ValueError(
                self._FACTOR_VALIDATION_ERROR
                + f"Received: input_number={input_number}"
            )

    def get_random_transformation(self, data, training=True, seed=None):
        if not training:
            return None

        if isinstance(data, dict):
            images = data["images"]
        else:
            images = data

        images_shape = self.backend.shape(images)
        if len(images_shape) == 3:
            batch_size = 1
        else:
            batch_size = images_shape[0]

        if seed is None:
            seed = self._get_seed_generator(self.backend._backend)

        invert = self.backend.random.uniform(
            minval=0,
            maxval=1,
            shape=[batch_size, 1],
            seed=seed,
            dtype=self.compute_dtype,
        )
        invert = self.backend.numpy.where(
            invert > 0.5,
            -self.backend.numpy.ones_like(invert),
            self.backend.numpy.ones_like(invert),
        )

        shear_y = self.backend.random.uniform(
            minval=self.y_factor[0],
            maxval=self.y_factor[1],
            shape=[batch_size, 1],
            seed=seed,
            dtype=self.compute_dtype,
        )
        shear_x = self.backend.random.uniform(
            minval=self.x_factor[0],
            maxval=self.x_factor[1],
            shape=[batch_size, 1],
            seed=seed,
            dtype=self.compute_dtype,
        )
        shear_factor = (
            self.backend.cast(
                self.backend.numpy.concatenate([shear_x, shear_y], axis=1),
                dtype=self.compute_dtype,
            )
            * invert
        )
        return {"shear_factor": shear_factor}

    def transform_images(self, images, transformation, training=True):
        images = self.backend.cast(images, self.compute_dtype)
        if training:
            return self._shear_inputs(images, transformation)
        return images

    def _shear_inputs(self, inputs, transformation):
        if transformation is None:
            return inputs

        inputs_shape = self.backend.shape(inputs)
        unbatched = len(inputs_shape) == 3
        if unbatched:
            inputs = self.backend.numpy.expand_dims(inputs, axis=0)

        shear_factor = transformation["shear_factor"]
        outputs = self.backend.image.affine_transform(
            inputs,
            transform=self._get_shear_matrix(shear_factor),
            interpolation=self.interpolation,
            fill_mode=self.fill_mode,
            fill_value=self.fill_value,
            data_format=self.data_format,
        )

        if unbatched:
            outputs = self.backend.numpy.squeeze(outputs, axis=0)
        return outputs

    def _get_shear_matrix(self, shear_factors):
        num_shear_factors = self.backend.shape(shear_factors)[0]

        # The shear matrix looks like:
        # [[1   s_x  0]
        #  [s_y  1   0]
        #  [0    0   1]]

        return self.backend.numpy.stack(
            [
                self.backend.numpy.ones((num_shear_factors,)),
                shear_factors[:, 0],
                self.backend.numpy.zeros((num_shear_factors,)),
                shear_factors[:, 1],
                self.backend.numpy.ones((num_shear_factors,)),
                self.backend.numpy.zeros((num_shear_factors,)),
                self.backend.numpy.zeros((num_shear_factors,)),
                self.backend.numpy.zeros((num_shear_factors,)),
            ],
            axis=1,
        )

    def transform_labels(self, labels, transformation, training=True):
        return labels

    def transform_bounding_boxes(
        self,
        bounding_boxes,
        transformation,
        training=True,
    ):
        raise NotImplementedError

    def transform_segmentation_masks(
        self, segmentation_masks, transformation, training=True
    ):
        return self.transform_images(
            segmentation_masks, transformation, training=training
        )

    def get_config(self):
        base_config = super().get_config()
        config = {
            "x_factor": self.x_factor,
            "y_factor": self.y_factor,
            "fill_mode": self.fill_mode,
            "interpolation": self.interpolation,
            "seed": self.seed,
            "fill_value": self.fill_value,
            "data_format": self.data_format,
        }
        return {**base_config, **config}

    def compute_output_shape(self, input_shape):
        return input_shape
